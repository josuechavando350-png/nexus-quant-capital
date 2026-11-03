"""Acumulado del Shadow en vivo: junta varias corridas y cuenta lo que hace falta para decidir si podríamos competir.

Una corrida en vivo dura unas 5.5 h y en ese rato caen pocas liquidaciones que se puedan pelear (las que el ganador se llevó
reaccionando en un trozo posterior al de la actualización del oráculo). Este módulo suma las carpetas `shadow-vivo` de varias
corridas y responde, con todas juntas: cuántas se podían pelear, qué ventana hubo entre la llegada de la actualización y la del
ganador (por WebSocket), si con lo que tardamos en decidir y un envío supuesto habríamos llegado antes, y cómo perdieron los
rivales. No toca la red: lee los archivos que dejó cada corrida.
"""

import hashlib
import json
import math
import os
import re
from collections import Counter

from .orden import clasificar
from .shadow_report import bot_key, competition, ms, read_json, read_jsonl, usd
from .shadow_live import quantiles

META_MUESTRA = 20           # mínimo de observaciones para revisar; no prueba estadística de rentabilidad
SUBMIT_MS = 20              # envío supuesto de la vía rápida (servidor cerca del secuenciador): no se mide, no se envía nada


def fine_ms(x):
    """Milisegundos con decimales (decidir lleva décimas de ms)."""
    return "—" if x is None else f"{x:g} ms"


def run_dirs(resultados, desde=None):
    """Carpetas `corridas/<id>/shadow-vivo` de una copia local de la rama de resultados, de la corrida `desde` en adelante."""
    base = os.path.join(resultados, "corridas")
    out = []
    for name in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        d = os.path.join(base, name, "shadow-vivo")
        if re.fullmatch(r"\d+", name) and os.path.isdir(d) and (desde is None or int(name) >= int(desde)):
            out.append(d)
    return sorted(out, key=lambda d: int(os.path.basename(os.path.dirname(d))))


def competable(r):
    """¿Se podía pelear? Directa y el ganador cayó en un trozo posterior al de la actualización (medido en vivo si se pudo;
    si no, por las propinas vecinas)."""
    if (r.get("via") or "") != "directa":
        return False
    f = r.get("flash") or {}
    if f.get("trozos_entre") is not None:
        return f["trozos_entre"] >= 1
    return clasificar(f.get("propinas")) == "trozo_siguiente"


def finite(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def event_key(r):
    """La identidad del evento es tx + log_index; una tx puede liquidar varias posiciones."""
    tx, idx = r.get("tx"), r.get("log_index")
    if isinstance(tx, str) and tx and isinstance(idx, int) and not isinstance(idx, bool) and idx >= 0:
        return tx.lower(), idx
    return None


def exact_timing(r):
    """Unir evidencia del mismo proceso, mercado, bloque y actualización; nunca imputar la mediana."""
    f = r.get("flash") or {}
    e = f.get("ws_decision") or {}
    if e.get("schema") != "nqc-shadow-log-window-v1":
        return None
    tx = (f.get("actualizacion_tx") or "").lower()
    if (not tx or e.get("actualizacion_tx") != tx or e.get("liquidacion_tx") != (r.get("tx") or "").lower()
            or e.get("mercado") != r.get("mercado") or e.get("bloque") != r.get("bloque_liquidacion")):
        return None
    if not all(finite(e.get(k)) for k in ("t_log", "t_liquidacion", "decision_ms", "ventana_ms")) or e["decision_ms"] < 0:
        return None
    matches = [u for u in r["_updates"].get(tx, [])
               if u.get("bloque") == e["bloque"] and r.get("mercado") in (u.get("mercados") or [])
               and u.get("t_log") == e["t_log"] and u.get("decision_ms") == e["decision_ms"]]
    if len(matches) != 1 or abs(round((e["t_liquidacion"] - e["t_log"]) * 1000, 1) - e["ventana_ms"]) > 0.051:
        return None
    return e


def admission_funnel(liqs, min_bono):
    """Causas excluyentes en orden: distingue escasez de oportunidades de falta de medición.

    No modifica los criterios de muestra ni elimina holguras negativas.
    El bono es bruto del evento de terceros, nunca P&L de NQC.
    """
    checks = (
        ("directas", "via_no_directa", lambda r: r.get("via") == "directa"),
        ("bono_minimo", "bono_inferior_o_no_medido", lambda r: finite(r.get("bono_usd")) and r["bono_usd"] >= min_bono),
        ("trozo_posterior_medido", "sin_trozo_posterior_medido",
         lambda r: finite((r.get("flash") or {}).get("trozos_entre")) and r["flash"]["trozos_entre"] >= 1),
        ("tiempos_origen_comun", "sin_tiempos_con_origen_comun", lambda r: exact_timing(r) is not None),
        ("integridad", "identidad_o_integridad_incompleta",
         lambda r: event_key(r) is not None and not r["_bad"] and not r["_conflict"]),
    )
    def count(stage, rows):
        return {"etapa": stage, "n": len(rows),
                "bono_bruto_usd": sum(r["bono_usd"] for r in rows if finite(r.get("bono_usd")))}
    remaining, reasons, cases = list(liqs), Counter(), []
    stages = [count("observadas_unicas", remaining)]
    for stage, reason, check in checks:
        accepted = []
        for r in remaining:
            if check(r):
                accepted.append(r)
            else:
                reasons[reason] += 1
                cases.append({"corrida": r["_run"], "tx": r.get("tx"), "log_index": r.get("log_index"),
                              "bono_bruto_usd": r.get("bono_usd"), "primera_exclusion": reason})
        remaining = accepted
        stages.append(count(stage, remaining))
    return {"etapas": stages, "primera_exclusion": dict(reasons), "casos_excluidos": cases,
            "orden_excluyente": True, "min_bono_usd": min_bono}


def acumulado(dirs, submit_ms=SUBMIT_MS, min_bono=1.0):
    if not finite(submit_ms) or submit_ms < 0 or not finite(min_bono) or min_bono < 0:
        raise ValueError("envío supuesto y bono mínimo deben ser finitos y no negativos")
    runs, liqs, crossings, seen, inputs = [], [], [], {}, []
    duplicates, conflicts, bad_lines = 0, 0, 0
    for d in dict.fromkeys(os.path.realpath(d) for d in dirs):
        bloques, bbad = read_jsonl(os.path.join(d, "bloques.jsonl"))
        res, rbad = read_jsonl(os.path.join(d, "resultados.jsonl"))
        rap, pbad = read_jsonl(os.path.join(d, "flash_rapido.jsonl"))
        upd, ubad = read_jsonl(os.path.join(d, "flash_actualizaciones.jsonl"))
        bad = bbad + rbad + pbad + ubad
        bad_lines += bad
        meta = read_json(os.path.join(d, "meta.json")) or {}
        run_id = os.path.basename(os.path.dirname(d))
        hashes = {}
        for name in ("bloques.jsonl", "resultados.jsonl", "flash_rapido.jsonl", "flash_actualizaciones.jsonl", "meta.json"):
            path = os.path.join(d, name)
            if os.path.isfile(path):
                with open(path, "rb") as fh:
                    hashes[name] = hashlib.sha256(fh.read()).hexdigest()
        inputs.append({"corrida": run_id, "sha256": hashes})
        ts = [b["ts"] for b in bloques if b.get("ts")]
        p50 = ((meta.get("via_rapida") or {}).get("decision_ms") or {}).get("p50")
        updates = {}
        for u in upd:
            if u.get("tx"):
                updates.setdefault(u["tx"].lower(), []).append(u)
        run_liqs = []
        for r in res:
            if "bloque_liquidacion" not in r:
                continue
            key = event_key(r)
            if key is not None and key in seen:
                duplicates += 1
                previous = {k: v for k, v in seen[key].items() if not k.startswith("_")}
                if r != previous:
                    seen[key]["_conflict"] = True
                    conflicts += 1
                continue
            row = dict(r, _decision_p50=p50, _updates=updates, _run=run_id, _bad=bad, _conflict=False)
            run_liqs.append(row)
            if key is not None:
                seen[key] = row
        runs.append({"corrida": run_id, "bloques": len(bloques), "lineas_invalidas": bad,
                     "horas": round((max(ts) - min(ts)) / 3600, 2) if ts else 0.0, "liquidaciones": len(run_liqs),
                     "via_rapida": bool(meta.get("via_rapida")), "decision_p50_ms": p50})
        liqs += run_liqs
        crossings += [x for x in rap if x.get("resultado") == "liquidada"]
    peleables = [r for r in liqs if competable(r)]
    measured = []
    for r in peleables:
        f = r.get("flash") or {}
        exact = exact_timing(r)
        w = exact["ventana_ms"] if exact else f.get("ws_ventana_ms")
        if not finite(w):
            continue
        # La ventana histórica hash→hash y la mediana son solo un escenario aproximado.
        dms = exact["decision_ms"] if exact else r["_decision_p50"]
        dms = dms if finite(dms) and dms >= 0 else None
        slack = None if dms is None else round(w - dms - submit_ms, 1)
        reasons = []
        if not exact:
            reasons.append("sin_tiempos_con_origen_comun")
        if not finite(f.get("trozos_entre")) or f["trozos_entre"] < 1:
            reasons.append("trozo_solo_inferido")
        if event_key(r) is None:
            reasons.append("sin_identidad_de_evento")
        if r["_bad"]:
            reasons.append("corrida_con_lineas_invalidas")
        if r["_conflict"]:
            reasons.append("observaciones_en_conflicto")
        measured.append({"etiqueta": r["etiqueta"], "bono_usd": r["bono_usd"], "tx": r["tx"], "ventana_ms": w, "decision_ms": dms,
                         "holgura_est_ms": slack, "propina_gwei": r.get("propina_gwei"), "corrida": r["_run"],
                         "log_index": r.get("log_index"), "origen": "log_misma_corrida" if exact else "hash_y_mediana",
                         "exclusiones_muestra": reasons})
    worth = [m for m in measured if m["bono_usd"] >= min_bono]
    on_time = [m for m in worth if m["holgura_est_ms"] is not None and m["holgura_est_ms"] > 0]
    sample = [m for m in worth if not m["exclusiones_muestra"]]
    sample_on_time = [m for m in sample if m["holgura_est_ms"] > 0]
    rivals = competition([{"bono_usd": r["bono_usd"], "clase": clasificar((r.get("flash") or {}).get("propinas")),
                           "intentos": (r.get("flash") or {}).get("intentos"), "ganador": bot_key(r.get("entrada"), r.get("firmante"))}
                          for r in liqs if (r.get("flash") or {}).get("intentos")])
    seen_ok = [x for x in crossings if x.get("holgura_ms") is not None]
    return {"schema": "nqc-shadow-acumulado-v2", "fuentes": inputs,
            "embudo_muestra": admission_funnel(liqs, min_bono),
            "calidad": {"eventos_duplicados": duplicates, "conflictos": conflicts, "lineas_invalidas": bad_lines},
            "muestra": {"n": len(sample), "meta": META_MUESTRA, "faltan": max(0, META_MUESTRA - len(sample)),
                        "estado": "LISTA_PARA_REVISION" if len(sample) >= META_MUESTRA else "INSUFICIENTE",
                        "a_tiempo_estimado": len(sample_on_time), "casos": sample,
                        "captura_demostrada": False, "rentabilidad_demostrada": False},
            "corridas": runs, "horas": round(sum(x["horas"] for x in runs), 2), "bloques": sum(x["bloques"] for x in runs),
            "liquidaciones": {"n": len(liqs), "bono_usd": sum(r["bono_usd"] for r in liqs),
                              "directas": sum(1 for r in liqs if (r.get("via") or "") == "directa")},
            "peleables": {"n": len(peleables), "bono_usd": sum(r["bono_usd"] for r in peleables),
                          "con_ventana": len(measured), "ventana_ms": quantiles([m["ventana_ms"] for m in measured]),
                          "min_bono_usd": min_bono, "que_valen": len(worth), "a_tiempo": len(on_time),
                          "bono_que_valen_usd": sum(m["bono_usd"] for m in worth), "bono_a_tiempo_usd": sum(m["bono_usd"] for m in on_time),
                          "holgura_est_ms": quantiles([m["holgura_est_ms"] for m in worth if m["holgura_est_ms"] is not None]),
                          "casos": sorted(measured, key=lambda m: -m["bono_usd"])[:12]},
            "via_rapida_vio_el_cruce": {"n": len(seen_ok), "positivas": sum(1 for x in seen_ok if x["holgura_ms"] > 0),
                                        "holgura_ms": quantiles([x["holgura_ms"] for x in seen_ok])},
            "rivales": rivals, "envio_supuesto_ms": submit_ms, "meta_muestra": META_MUESTRA}


def render(a):
    p, lq = a["peleables"], a["liquidaciones"]
    L = [f"# Shadow acumulado · {len(a['corridas'])} corridas en vivo, {a['horas']:.1f} h", "",
         "> Solo lectura. No se firmó ni se envió nada. «A tiempo» quiere decir que, con lo que tardamos en decidir y "
         f"{a['envio_supuesto_ms']} ms supuestos de red (ver el trozo y enviar desde un servidor cerca del secuenciador; no se mide), nuestra "
         "transacción habría llegado antes de que se publicara el trozo del ganador. Es una cota optimista: el trozo se cierra un poco antes de "
         "publicarse, y dentro del trozo gana la propina más alta, que aquí no entra.", "",
         f"- Liquidaciones reales vistas: {lq['n']} ({usd(lq['bono_usd'])} de bono), {lq['directas']} directas.",
         f"- Peleables (el ganador reaccionó en un trozo posterior al de la actualización del oráculo): {p['n']} ({usd(p['bono_usd'])}).",
         f"- Con la ventana medida por WebSocket: {p['con_ventana']}; mediana {ms(p['ventana_ms']['p50'])}"
         + (f", mín {ms(p['ventana_ms']['min'])}, máx {ms(p['ventana_ms']['max'])}" if p["ventana_ms"]["n"] else "") + ".",
         f"- Con bono de {usd(p['min_bono_usd'])} o más: {p['que_valen']}; en el escenario aproximado habríamos llegado a tiempo para el trozo del ganador en "
         f"{p['a_tiempo']} ({usd(p['bono_a_tiempo_usd'])} de {usd(p['bono_que_valen_usd'])})"
         + (f"; holgura mediana {ms(p['holgura_est_ms']['p50'])}" if p["holgura_est_ms"]["n"] else "") + ".",
         f"- Muestra: {a['muestra']['n']} de {a['meta_muestra']} casos con evento único, trozos medidos y tiempos con origen común; "
         f"faltan {a['muestra']['faltan']}. Estado: {a['muestra']['estado']}.",
         f"- En esa muestra, holgura estimada positiva en {a['muestra']['a_tiempo_estimado']}. El envío sigue siendo supuesto.",
         "- La mediana de una corrida y la clasificación inferida por propinas no cuentan para la meta. "
         "Veinte observaciones solo abren una revisión: no certifican captura, inclusión ni rentabilidad.",
         f"- Calidad: {a['calidad']['eventos_duplicados']} eventos duplicados omitidos; {a['calidad']['conflictos']} conflictos; "
         f"{a['calidad']['lineas_invalidas']} líneas inválidas. Los archivos de entrada quedan identificados por SHA-256."]
    v = a["via_rapida_vio_el_cruce"]
    if a.get("embudo_muestra"):
        L += ["", "## Dónde se reduce la muestra", "",
              "Filtros consecutivos; los casos excluidos se atribuyen al primer filtro que falla. "
              "El bono es de liquidaciones de terceros, no beneficio propio.", "",
              "| Etapa | Casos restantes | Bono bruto |", "|---|---:|---:|"]
        L += [f"| {s['etapa']} | {s['n']} | {usd(s['bono_bruto_usd'])} |" for s in a["embudo_muestra"]["etapas"]]
    if v["n"]:
        L.append(f"- La vía rápida vio cruzar la posición antes que el ganador la liquidara en {v['n']} casos; holgura positiva en {v['positivas']} "
                 f"(mediana {ms(v['holgura_ms']['p50'])}).")
    rv = a["rivales"]
    if rv["liquidaciones"]:
        sg = rv["segundo"]
        late = sum((sg.get(k) or {}).get("n", 0) for k in ("trozo_posterior", "tarde_con_mas_propina"))
        L.append(f"- Rivales: en {rv['con_rivales']} de {rv['liquidaciones']} liquidaciones otro bot lo intentó y perdió; el segundo perdió por llegar "
                 f"tarde en {late} y por pagar menos en el mismo trozo en {(sg.get('mismo_trozo_menos_propina') or {}).get('n', 0)}.")
    if p["casos"]:
        L += ["", "| Mercado | Bono | Ventana | Decidir | Holgura (est.) | Origen |", "|---|---|---|---|---|---|"]
        L += [f"| {c['etiqueta']} | {usd(c['bono_usd'])} | {fine_ms(c['ventana_ms'])} | {fine_ms(c['decision_ms'])} | {fine_ms(c['holgura_est_ms'])} | {c['origen']} |"
              for c in p["casos"]]
    L += ["", "Corridas: " + ", ".join(f"{r['corrida']} ({r['horas']:.1f} h, {r['liquidaciones']} liq.)" for r in a["corridas"]) + "."]
    return "\n".join(L) + "\n"


def write(a, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    md = render(a)
    with open(os.path.join(out_dir, "ACUMULADO.md"), "w", encoding="utf-8") as fh:
        fh.write(md)
    with open(os.path.join(out_dir, "acumulado.json"), "w", encoding="utf-8") as fh:
        json.dump(a, fh, indent=2, sort_keys=True, default=str)
    return md

