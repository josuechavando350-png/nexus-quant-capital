"""Acumulado del Shadow en vivo: junta varias corridas y cuenta lo que hace falta para decidir si podríamos competir.

Una corrida en vivo dura unas 5.5 h y en ese rato caen pocas liquidaciones que se puedan pelear (las que el ganador se llevó
reaccionando en un trozo posterior al de la actualización del oráculo). Este módulo suma las carpetas `shadow-vivo` de varias
corridas y responde, con todas juntas: cuántas se podían pelear, qué ventana hubo entre la llegada de la actualización y la del
ganador (por WebSocket), si con lo que tardamos en decidir y un envío supuesto habríamos llegado antes, y cómo perdieron los
rivales. No toca la red: lee los archivos que dejó cada corrida.
"""

import json
import os
import re

from .orden import clasificar
from .shadow_report import bot_key, competition, ms, read_json, read_jsonl, usd
from .shadow_live import quantiles

META_MUESTRA = 20           # liquidaciones peleables con la ventana medida para decidir con algo de confianza
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


def acumulado(dirs, submit_ms=SUBMIT_MS, min_bono=1.0):
    runs, liqs, crossings, decide = [], [], [], {}
    for d in dirs:
        bloques, _ = read_jsonl(os.path.join(d, "bloques.jsonl"))
        res, _ = read_jsonl(os.path.join(d, "resultados.jsonl"))
        rap, _ = read_jsonl(os.path.join(d, "flash_rapido.jsonl"))
        upd, _ = read_jsonl(os.path.join(d, "flash_actualizaciones.jsonl"))
        meta = read_json(os.path.join(d, "meta.json")) or {}
        ts = [b["ts"] for b in bloques if b.get("ts")]
        p50 = ((meta.get("via_rapida") or {}).get("decision_ms") or {}).get("p50")
        run_liqs = [dict(r, _decision_p50=p50) for r in res if "bloque_liquidacion" in r]
        for u in upd:
            if u.get("tx"):
                decide[u["tx"].lower()] = u.get("decision_ms")
        runs.append({"corrida": os.path.basename(os.path.dirname(d)), "bloques": len(bloques),
                     "horas": round((max(ts) - min(ts)) / 3600, 2) if ts else 0.0, "liquidaciones": len(run_liqs),
                     "via_rapida": bool(meta.get("via_rapida")), "decision_p50_ms": p50})
        liqs += run_liqs
        crossings += [x for x in rap if x.get("resultado") == "liquidada"]
    peleables = [r for r in liqs if competable(r)]
    measured = []
    for r in peleables:
        f = r.get("flash") or {}
        w = f.get("ws_ventana_ms")
        if w is None:
            continue
        dms = decide.get((f.get("actualizacion_tx") or "").lower())
        dms = r["_decision_p50"] if dms is None else dms
        slack = None if dms is None else round(w - dms - submit_ms, 1)
        measured.append({"etiqueta": r["etiqueta"], "bono_usd": r["bono_usd"], "tx": r["tx"], "ventana_ms": w, "decision_ms": dms,
                         "holgura_est_ms": slack, "propina_gwei": r.get("propina_gwei")})
    worth = [m for m in measured if m["bono_usd"] >= min_bono]
    on_time = [m for m in worth if m["holgura_est_ms"] is not None and m["holgura_est_ms"] > 0]
    rivals = competition([{"bono_usd": r["bono_usd"], "clase": clasificar((r.get("flash") or {}).get("propinas")),
                           "intentos": (r.get("flash") or {}).get("intentos"), "ganador": bot_key(r.get("entrada"), r.get("firmante"))}
                          for r in liqs if (r.get("flash") or {}).get("intentos")])
    seen_ok = [x for x in crossings if x.get("holgura_ms") is not None]
    return {"corridas": runs, "horas": round(sum(x["horas"] for x in runs), 2), "bloques": sum(x["bloques"] for x in runs),
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
         f"- Con bono de {usd(p['min_bono_usd'])} o más: {p['que_valen']}; habríamos llegado a tiempo para el trozo del ganador en "
         f"{p['a_tiempo']} ({usd(p['bono_a_tiempo_usd'])} de {usd(p['bono_que_valen_usd'])})"
         + (f"; holgura mediana {ms(p['holgura_est_ms']['p50'])}" if p["holgura_est_ms"]["n"] else "") + ".",
         f"- Muestra: {p['que_valen']} de {a['meta_muestra']} casos para decidir con algo de confianza."]
    v = a["via_rapida_vio_el_cruce"]
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
        L += ["", "| Mercado | Bono | Ventana | Decidir | Holgura (est.) |", "|---|---|---|---|---|"]
        L += [f"| {c['etiqueta']} | {usd(c['bono_usd'])} | {ms(c['ventana_ms'])} | {fine_ms(c['decision_ms'])} | {ms(c['holgura_est_ms'])} |"
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

