"""Reporte del Shadow Base/Morpho: junta el modo en vivo y el replay y contesta la pregunta de la fase.

    ¿Llegaríamos a tiempo y con margen?

Separa lo medido (latencia desde donde corre, distancia entre el cruce y la liquidación, paridad de la
matemática, lo que ocurrió en vivo) de lo supuesto (tiempo de envío, retención del bono). Todo sale de los
archivos que escriben shadow_live y shadow_replay; este módulo no toca la red.
"""

import json
import math
import os
import time
from collections import Counter

from .analyze import num, pct, short, usd
from .config import SHADOW_BASE_MARKETS, SHADOW_PRIORS_SOURCE
from .rpc import ALLOWED_METHODS
from .orden import CLASES, analyze_order, clasificar, validate_classifier
from .shadow_live import AUCTION_ENTRIES, DEFAULTS, quantiles

BLOCK_MS = int(DEFAULTS["block_time_s"] * 1000)
MIN_SAMPLE = 30           # por debajo, una proporción se marca como muestra pequeña

# Distancia entre el cruce y la liquidación, en bloques.
BUCKETS = (("0", "mismo bloque", 0, 0), ("1", "1 bloque", 1, 1), ("2", "2 bloques", 2, 2),
           ("3-5", "3 a 5 bloques", 3, 5), ("6-15", "6 a 15 bloques", 6, 15), ("16+", "16 o más", 16, None))
# Días hacia atrás que podría mirar el libro al armarse, para medir qué parte de los prestatarios liquidados conocería.
LIBRO_DIAS = (7, 30, 60, 90)
# Tiempo total desde el bloque del cruce hasta que nuestra transacción llega, y el primer bloque en que cae.
LANDINGS = ((1, "hasta 2 s"), (2, "hasta 4 s"), (3, "hasta 6 s"))

# Métodos de RPC de solo lectura: los que el cliente deja pasar (rpc.ALLOWED_METHODS) y otros de lectura comunes.
READ_ONLY = set(ALLOWED_METHODS) | {"eth_getBlockByHash", "eth_getBalance", "eth_gasPrice", "eth_feeHistory",
                                    "eth_maxPriorityFeePerGas", "net_version", "web3_clientVersion", "eth_syncing",
                                    "eth_subscribe", "eth_unsubscribe"}
DANGEROUS_PREFIXES = ("eth_send", "eth_sign", "personal_", "eth_accounts", "eth_submit", "eth_signTransaction",
                      "debug_setHead", "miner_", "admin_", "txpool_")


# --- Lectura ----------------------------------------------------------------------------
def read_jsonl(path):
    """Filas de un JSONL; una última línea cortada por una cancelación se cuenta y se ignora."""
    rows, bad = [], 0
    if not os.path.exists(path):
        return rows, bad
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                bad += 1
    return rows, bad


def read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


# --- Utilidades -------------------------------------------------------------------------
def weight(r):
    return r.get("peso") or 1.0


def wsum(rows, key):
    return sum(weight(r) * (r.get(key) or 0.0) for r in rows)


def wcount(rows):
    return sum(weight(r) for r in rows)


def median(xs):
    xs = sorted(xs)
    return None if not xs else xs[len(xs) // 2] if len(xs) % 2 else (xs[len(xs) // 2 - 1] + xs[len(xs) // 2]) / 2


def share(part, whole):
    return part / whole if whole else None


def arrival(delta, k):
    """Contra quien liquidó de verdad: llegamos antes, en el mismo bloque (empate) o tarde."""
    return "antes" if delta > k else "empate" if delta == k else "tarde"


def way(r):
    return r.get("via") or "sin_via"


def eligible(r, cfg):
    return (way(r) == "directa" and not r.get("deuda_mala") and (r.get("bono_usd") or 0) >= cfg["min_bonus_usd"]
            and (r.get("neto_modelo_usd") or 0) >= cfg["min_net_usd"])


def bucket_rows(rows, lo, hi):
    return [r for r in rows if r["delta_bloques"] >= lo and (hi is None or r["delta_bloques"] <= hi)]


# --- Replay -----------------------------------------------------------------------------
def analyze_replay(rows, errors, meta, cfg):
    meta = meta or {}
    usable = [r for r in rows if not r.get("sin_dato")]
    exact = [r for r in usable if not r.get("censurado")]
    censored = [r for r in usable if r.get("censurado")]
    out = {"filas": len(rows), "sin_dato": len(rows) - len(usable), "censuradas": len(censored), "errores": len(errors),
           "residuales": sum(1 for r in usable if r.get("residual_de_liquidacion_parcial")),
           "meta": {k: meta.get(k) for k in ("eventos_en_ventana", "elegibles", "elegidos", "procesados", "fallidos",
                                              "omitidos_por_tiempo", "bono_total_usd", "bono_elegible_usd", "bono_elegido_usd",
                                              "ventana", "segundos", "sondeos_de_archivo")}}
    by_delta = []
    for key, label, lo, hi in BUCKETS:
        sel = bucket_rows(exact, lo, hi)
        direct = [r for r in sel if way(r) == "directa"]
        auction = [r for r in sel if way(r) == "subasta"]
        by_delta.append({"tramo": key, "etiqueta": label, "n": len(sel), "n_directa": len(direct), "n_subasta": len(auction),
                         "bono_directo_est_usd": wsum(direct, "bono_usd"), "bono_subasta_est_usd": wsum(auction, "bono_usd")})
    total_direct = sum(b["bono_directo_est_usd"] for b in by_delta)
    for b in by_delta:
        b["parte_del_bono_directo"] = share(b["bono_directo_est_usd"], total_direct)
    out["por_distancia"] = by_delta

    el = [r for r in exact if eligible(r, cfg)]
    landings = []
    for k, label in LANDINGS:
        groups = {"antes": [], "empate": [], "tarde": []}
        for r in el:
            groups[arrival(r["delta_bloques"], k)].append(r)
        total_n, total_bono = wcount(el), wsum(el, "bono_usd")
        row = {"k": k, "tiempo_total": label}
        for g, sel in groups.items():
            row[g] = {"n": len(sel), "n_est": wcount(sel), "bono_est_usd": wsum(sel, "bono_usd"), "neto_est_usd": wsum(sel, "neto_modelo_usd"),
                      "parte_n": share(wcount(sel), total_n), "parte_bono": share(wsum(sel, "bono_usd"), total_bono)}
        landings.append(row)
    cens_el = [r for r in censored if eligible(r, cfg)]
    out["ganables"] = {"elegibles": len(el), "elegibles_est": wcount(el), "bono_est_usd": wsum(el, "bono_usd"),
                       "neto_est_usd": wsum(el, "neto_modelo_usd"),
                       "por_tiempo_total": landings,
                       "censuradas": {"n": len(cens_el), "bono_est_usd": wsum(cens_el, "bono_usd")},
                       "muestra_pequena": len(el) < MIN_SAMPLE}

    routes = Counter(way(r) for r in usable)
    out["vias"] = {v: {"n": n, "bono_est_usd": wsum([r for r in usable if way(r) == v], "bono_usd")} for v, n in routes.items()}

    markets = []
    for label in sorted({r["etiqueta"] for r in exact}):
        sel = [r for r in exact if r["etiqueta"] == label]
        direct = [r for r in sel if way(r) == "directa"]
        deltas = [r["delta_bloques"] for r in direct]
        markets.append({"mercado": label, "n": len(sel), "n_directa": len(direct), "bono_directo_est_usd": wsum(direct, "bono_usd"),
                        "mediana_bloques": median(deltas), "parte_2_o_mas": share(sum(1 for d in deltas if d >= 2), len(deltas))})
    markets.sort(key=lambda m: -m["bono_directo_est_usd"])
    out["por_mercado"] = markets

    direct_all = [r for r in exact if way(r) == "directa"]
    out["costos_del_ganador"] = {
        "gas_usd": quantiles([r["gas_usd"] for r in direct_all if r.get("gas_usd") is not None]),
        "propina_usd": quantiles([r["propina_usd"] for r in direct_all if r.get("propina_usd") is not None]),
        "nota": "gas y propina que pagó quien liquidó (no los nuestros)"}
    out["distancia_directas"] = quantiles([r["delta_bloques"] for r in direct_all])

    par = [r["paridad"] for r in rows if r.get("paridad")]
    used = [p for p in par if "modo" in p]
    errs = sorted(max(p["err_embargo"], p["err_shares"], p["err_repago"]) for p in used)
    out["paridad"] = {"n": len(errs), "omitidas": dict(Counter(p["omitida"] for p in par if "omitida" in p)),
                      "max": errs[-1] if errs else None, "mediana": median(errs), "exactas": sum(1 for e in errs if e == 0),
                      "dentro_1e9": sum(1 for e in errs if e <= 1e-9), "dentro_1e6": sum(1 for e in errs if e <= 1e-6),
                      "con_interes": sum(1 for p in used if p.get("con_interes")),
                      "peores": sorted(({"tx": r["tx"], "mercado": r["etiqueta"], "error": max(r["paridad"]["err_embargo"], r["paridad"]["err_shares"],
                                                                                              r["paridad"]["err_repago"])}
                                        for r in rows if r.get("paridad") and "modo" in r["paridad"]), key=lambda x: -x["error"])[:5]}

    # ¿Quién se lleva el bono directo y en cuántos días cae? (con peso: la muestra representa toda la ventana)
    direct_rows = [r for r in usable if way(r) == "directa"]
    by_winner = Counter()
    for r in direct_rows:
        by_winner[r.get("firmante") or r.get("liquidador") or "?"] += weight(r) * (r.get("bono_usd") or 0.0)
    total_w = sum(by_winner.values())
    ranked = by_winner.most_common()
    out["ganadores"] = {"distintos": len(by_winner), "bono_est_usd": total_w,
                        "top1": share(ranked[0][1], total_w) if ranked else None,
                        "top3": share(sum(v for _, v in ranked[:3]), total_w) if ranked else None,
                        "top10": share(sum(v for _, v in ranked[:10]), total_w) if ranked else None}
    start_block = (meta.get("ventana") or {}).get("desde")
    per_day = Counter()
    if direct_rows:
        origin = start_block if start_block is not None else min(r["bloque_liquidacion"] for r in direct_rows)
        blocks_per_day = int(86400 / DEFAULTS["block_time_s"])
        for r in direct_rows:
            per_day[max(0, (r["bloque_liquidacion"] - origin) // blocks_per_day)] += weight(r) * (r.get("bono_usd") or 0.0)
    total_d = sum(per_day.values())
    days_ranked = per_day.most_common()
    out["concentracion_dias"] = {"dias_con_liquidaciones": len(per_day), "bono_est_usd": total_d,
                                 "top1": share(days_ranked[0][1], total_d) if days_ranked else None,
                                 "top3": share(sum(v for _, v in days_ranked[:3]), total_d) if days_ranked else None}

    out["flashblocks"] = meta.get("flashblocks")
    scan = meta.get("borrow_scan") or {}
    if scan.get("completo") and rows:
        table_ = []
        for days in LIBRO_DIAS:
            # Solo cuentan las liquidaciones con al menos esa historia disponible antes de ellas en lo escaneado.
            pool = [r for r in rows if r.get("libro_historia_dias") is not None and r["libro_historia_dias"] >= days]
            cov = [r for r in pool if r.get("libro_edad_dias") is not None and r["libro_edad_dias"] <= days]
            table_.append({"dias": days, "n": len(pool), "parte_n": share(wcount(cov), wcount(pool)),
                           "parte_bono": share(wsum(cov, "bono_usd"), wsum(pool, "bono_usd"))})
        out["cobertura_libro"] = {"por_dias_atras": table_, "escaneado_desde": scan.get("desde"), "borrows": scan.get("borrows"),
                                  "mas_viejos_que_lo_escaneado": sum(1 for r in rows if r.get("libro_edad_dias") is None)}

    # Control cruzado contra el Census: el bono directo estimado por el replay debe parecerse al del Census.
    ids = set((meta.get("mercados") or {}).keys())
    days = (meta.get("ventana") or {}).get("dias") or (meta.get("config") or {}).get("dias") or 30
    census = sum(m["dir_bonus"] for m in SHADOW_BASE_MARKETS if not ids or m["id"] in ids) * days / 30
    est = wsum([r for r in rows if way(r) == "directa"], "bono_usd")
    out["control_census"] = {"bono_directo_replay_est_usd": est, "bono_directo_census_usd": census, "razon": share(est, census),
                             "nota": "el replay solo cuenta liquidaciones de al menos el mínimo de bono; el Census cuenta todas"}
    return out


SEPARATION_STEPS = ((1, "hasta 1 tx"), (10, "hasta 10 tx"), (100, "hasta 100 tx"), (None, "más de 100 tx"))


def separation(rows):
    """Cuánto después de la actualización del oráculo cae la liquidación, dentro del mismo bloque: en transacciones y en
    parte del bloque (que aproxima el tiempo si las transacciones se reparten parejo en los 2 s)."""
    def one(rs):
        g = [r["tx_entre_actualizacion_y_liquidacion"] for r in rs]
        f = [r["fraccion_del_bloque"] for r in rs if r["fraccion_del_bloque"] is not None]
        steps, lo = {}, -1
        for hi, label in SEPARATION_STEPS:
            steps[label] = sum(1 for x in g if x > lo and (hi is None or x <= hi))
            lo = hi if hi is not None else lo
        return {"n": len(g), "tx": quantiles(g), "fraccion": quantiles(f),
                "ms_aprox": quantiles([x * BLOCK_MS for x in f]), "tramos": steps}
    same = [r for r in rows if r["tx_entre_actualizacion_y_liquidacion"] is not None and r["tx_entre_actualizacion_y_liquidacion"] >= 0]
    out = {"todas": one(same), "por_via": {}}
    for via in ("subasta", "normal"):
        part = [r for r in same if r["via_actualizacion"] == via]
        if part:
            out["por_via"][via] = one(part)
    prio = Counter(r["prioridad_vs_actualizacion"] for r in same if r["prioridad_vs_actualizacion"])
    out["prioridad_de_la_liquidacion_vs_actualizacion"] = dict(prio)
    # Con cuánto bono (estimado con los pesos de la muestra del replay, si los hay) se queda cada caso: pagar más prioridad que la
    # actualización y caer después implica un trozo posterior (reaccionó); la misma prioridad es lo típico de lo empaquetado con ella.
    wt = lambda r: r["peso"] if r.get("peso") is not None else 1.0                                       # noqa: E731
    tagged = [r for r in same if r["prioridad_vs_actualizacion"]]
    total = sum((r.get("bono_usd") or 0.0) * wt(r) for r in tagged)
    out["por_prioridad"] = {}
    for tag in ("mayor", "igual", "menor"):
        part = [r for r in tagged if r["prioridad_vs_actualizacion"] == tag]
        b = sum((r.get("bono_usd") or 0.0) * wt(r) for r in part)
        out["por_prioridad"][tag] = {"n": len(part), "bono_est_usd": b, "parte_del_bono": share(b, total)}
    out["con_pesos"] = bool(tagged) and all(r.get("peso") is not None for r in tagged)
    # Clase de cada liquidación según las propinas vecinas (ver orden.clasificar): empaquetada / en el mismo trozo / en un trozo posterior / ambigua
    classed = [r for r in same if r.get("clase")]
    total_c = sum((r.get("bono_usd") or 0.0) * wt(r) for r in classed)
    out["por_clase"] = {}
    for k in CLASES:
        part = [r for r in classed if r["clase"] == k]
        b = sum((r.get("bono_usd") or 0.0) * wt(r) for r in part)
        out["por_clase"][k] = {"n": len(part), "bono_est_usd": b, "parte_del_bono": share(b, total_c)}
    return out


def analyze_diag(diag_rows, oracles=None, weights=None):
    """Qué pasó con el precio y los feeds del oráculo justo antes de cada liquidación directa mirada con lupa.
    `weights` {(tx, mercado, prestatario): peso} son los pesos de la muestra del replay, para estimar bonos de todo el período."""
    ok = [d for d in diag_rows if "serie" in d]
    out = {"n": len(ok), "errores": len(diag_rows) - len(ok), "oraculos": {}}
    rows, gaps = [], []
    for d in ok:
        b = d["bloque_liquidacion"]
        by = {x["bloque"]: x for x in d["serie"]}
        prev, cur = by.get(b - 1), by.get(b)
        liq_prev = None if not prev else prev["liquidable"]
        price_changed = None
        feed_changed = None
        if prev and cur and prev["precio"] is not None and cur["precio"] is not None:
            price_changed = cur["precio"] != prev["precio"]
        if prev and cur and prev["feeds"] and cur["feeds"]:
            feed_changed = any(cur["feeds"].get(g, {}).get("ronda") != p_.get("ronda") for g, p_ in prev["feeds"].items())
        last_change = None                                   # bloques entre el último cambio de feed y la liquidación
        ks = sorted(by)
        for a, c in zip(ks, ks[1:]):
            if c > b:
                continue
            fa, fc = by[a]["feeds"], by[c]["feeds"]
            if fa and fc and any(fc.get(g, {}).get("ronda") != x.get("ronda") for g, x in fa.items()):
                last_change = b - c
        upd = d.get("actualizacion_previa")
        gap = None if not upd else d["tx_index"] - upd["tx_index"]
        if gap is not None:
            gaps.append(gap)
        n_tx = d.get("bloque_n_tx")
        prio_l, prio_u = d.get("prioridad_wei"), (upd or {}).get("prioridad_wei")
        rows.append({"etiqueta": d["etiqueta"], "bloque": b, "bono_usd": d.get("bono_usd"),
                     "peso": (weights or {}).get((d.get("tx"), d.get("mercado"), d.get("prestatario"))),
                     "liquidable_un_bloque_antes": liq_prev, "precio_cambio_en_el_bloque": price_changed,
                     "feed_cambio_en_el_bloque": feed_changed, "bloques_desde_el_ultimo_cambio_de_feed": last_change,
                     "tx_entre_actualizacion_y_liquidacion": gap,
                     "bloque_n_tx": n_tx, "fraccion_del_bloque": gap / n_tx if gap is not None and n_tx else None,
                     "clase": clasificar(d.get("propinas")),
                     "via_actualizacion": None if not upd else ("subasta" if upd.get("to") in AUCTION_ENTRIES else "normal"),
                     "prioridad_vs_actualizacion": None if prio_l is None or prio_u is None else
                     ("mayor" if prio_l > prio_u else "igual" if prio_l == prio_u else "menor"),
                     "mismo_actor": None if not upd else (upd["from"] == (d.get("firmante") or "").lower() or upd["to"] == (d.get("entrada") or "").lower())})
    out["filas"] = rows
    out["liquidable_un_bloque_antes"] = sum(1 for r in rows if r["liquidable_un_bloque_antes"])
    out["precio_cambio_en_el_bloque"] = sum(1 for r in rows if r["precio_cambio_en_el_bloque"])
    out["feed_cambio_en_el_bloque"] = sum(1 for r in rows if r["feed_cambio_en_el_bloque"])
    out["con_actualizacion_antes_en_el_bloque"] = len(gaps)
    out["tx_entre_actualizacion_y_liquidacion_mediana"] = median(gaps)
    out["mismo_actor"] = sum(1 for r in rows if r["mismo_actor"])
    out["separacion"] = separation(rows)
    for addr, o in (oracles or {}).items():
        out["oraculos"][addr] = {g: (d.get("descripcion"), d.get("direccion")) for g, d in (o.get("detalle") or {}).items()}
    return out


# --- En vivo ----------------------------------------------------------------------------
def flash_profile(perfiles, n_tx=None):
    """Cómo se llena un bloque de Base en el estado pendiente: transacciones por bloque y por trozo, y la parte del bloque que
    llevan acumulada los trozos. Solo con bloques vistos desde el principio (la primera foto traía pocas transacciones).
    `n_tx` {bloque: transacciones del bloque sellado} corrige el total si el último trozo se escapó entre dos fotos."""
    n_tx = n_tx or {}
    full = [p for p in perfiles if p.get("trozos") and p.get("primera_foto", 10 ** 9) <= 5]
    sizes, finals, counts, frac, last_seen = [], [], [], {}, []
    for p in full:
        cum = [n for _, n in p["trozos"]]
        total = max(n_tx.get(p["bloque"]) or 0, cum[-1])
        finals.append(total)
        counts.append(len(cum))
        if n_tx.get(p["bloque"]):
            last_seen.append(cum[-1] >= 0.98 * total)         # ¿el último trozo observado ya traía (casi) todo el bloque?
        prev = 0
        for k, n in enumerate(cum):
            sizes.append(n - prev)
            prev = n
            frac.setdefault(k, []).append(n / total)
    return {"bloques": len(perfiles), "completos": len(full), "txs_por_bloque": quantiles(finals), "trozos_por_bloque": quantiles(counts),
            "txs_por_trozo": quantiles(sizes), "fraccion_acumulada_p50": [quantiles(v)["p50"] for _, v in sorted(frac.items())],
            "ultimo_trozo_completo": None if not last_seen else sum(last_seen) / len(last_seen)}


def analyze_live(bloques, decisiones, resultados, sistema, cercanas, meta, cfg, cruces=None, perfiles=None, rapido=None):
    meta = meta or {}
    out = {}
    numbers = sorted({b["bloque"] for b in bloques})
    stamps = [b["ts"] for b in bloques if b.get("ts")]
    span = (numbers[-1] - numbers[0] + 1) if numbers else 0
    out["ventana"] = {"bloques": len(numbers), "bloques_en_rango": span, "cobertura": share(len(numbers), span),
                      "desde_bloque": numbers[0] if numbers else None, "hasta_bloque": numbers[-1] if numbers else None,
                      "desde_ts": min(stamps) if stamps else None, "hasta_ts": max(stamps) if stamps else None,
                      "horas": (max(stamps) - min(stamps)) / 3600 if stamps else 0.0}
    visto = [b["visto_ms"] for b in bloques if b.get("visto_ms") is not None]
    out["latencia"] = {
        "visto_ms": quantiles(visto),
        "proceso_ms": quantiles([b["total_ms"] for b in bloques if b.get("total_ms") is not None]),
        "visto_mas_proceso_ms": quantiles([b["visto_ms"] + b["total_ms"] for b in bloques if b.get("visto_ms") is not None]),
        "fases_ms": {f: quantiles([b[f] for b in bloques if b.get(f) is not None])
                     for f in ("cabecera_ms", "logs_ms", "lectura_ms", "evaluar_ms")},
        "decision": {"visto_ms": quantiles([d["visto_ms"] for d in decisiones if d.get("visto_ms") is not None]),
                     "decidido_ms": quantiles([d["decidido_ms"] for d in decisiones if d.get("decidido_ms") is not None]),
                     "x_ms": quantiles([d["x_ms"] for d in decisiones if d.get("x_ms") is not None]),
                     "bloque_de_llegada": dict(Counter(d["bloque_llegada_propia"] - d["bloque_cruce"] for d in decisiones
                                                       if d.get("bloque_llegada_propia") is not None))},
        "nota": "visto_ms es cota superior: el timestamp del bloque tiene resolución de 1 s; se mide desde un servidor de GitHub Actions"}

    out["decisiones"] = {"por_decision": dict(Counter(d["decision"] for d in decisiones)),
                         "por_razon": {f"{d}:{r}": n for (d, r), n in sorted(Counter((d["decision"], d["razon"]) for d in decisiones).items())}}
    by_id = {r["id"]: r for r in resultados if r.get("id")}
    go = [d for d in decisiones if d["decision"] == "GO"]
    fate = Counter((by_id.get(d["id"]) or {}).get("resultado", "sin_cierre") for d in go)
    liq_go_all = [by_id[d["id"]] for d in go if (by_id.get(d["id"]) or {}).get("resultado") == "liquidada"]
    liq_go = [r for r in liq_go_all if not r.get("cruce_incierto")]          # sin hora de cruce conocida no hay carrera que medir
    arrivals = {}
    for g in ("antes", "empate", "tarde"):
        sel = [r for r in liq_go if r.get("llegada") == g]
        arrivals[g] = {"n": len(sel), "bono_usd": sum(r["bono_usd"] for r in sel), "neto_modelo_usd": sum(r.get("neto_modelo_usd") or 0 for r in sel)}
    out["go"] = {"n": len(go), "destino": dict(fate), "llegada_medida": arrivals,
                 "con_cruce_incierto": sum(1 for d in go if d.get("cruce_incierto")),
                 "liquidadas_con_cruce_incierto": len(liq_go_all) - len(liq_go),
                 "liquidadas_por_subasta": sum(1 for r in liq_go if r.get("via") == "subasta"),
                 "bono_usd": sum(d["bono_usd"] for d in go), "neto_modelo_usd": sum(d["neto_modelo_usd"] for d in go),
                 "cerrados": sum(n for k, n in fate.items() if k not in ("sin_cierre", "abierta_al_cierre"))}

    liqs = [r for r in resultados if "bloque_liquidacion" in r]
    kinds = Counter((r.get("clase") or "con_aviso") for r in liqs)
    seen = kinds.get("con_aviso", 0) + kinds.get("tras_expirar", 0)
    out["liquidaciones"] = {
        "n": len(liqs), "bono_usd": sum(r["bono_usd"] for r in liqs), "clases": dict(kinds),
        "vias": dict(Counter(way(r) for r in liqs)),
        "recall_visibles": share(seen, seen + kinds.get("fuera_del_libro", 0)),
        "parte_mismo_bloque": share(kinds.get("mismo_bloque", 0), len(liqs)),
        "fuera_del_libro": [{"mercado": r["etiqueta"], "prestatario": r["prestatario"], "bono_usd": r["bono_usd"], "tx": r["tx"]}
                            for r in liqs if r.get("clase") == "fuera_del_libro"][:10]}
    fl = [r for r in liqs if r.get("flash")]
    if fl or meta.get("flashblocks"):
        def kind(r):
            f = r["flash"]
            if not f.get("visto"):
                return "no_visto"
            if "trozos_entre" not in f:
                return "sin_actualizacion"                 # no se encontró la actualización del feed antes, en ese bloque
            return "mismo_trozo" if f["trozos_entre"] <= 0 else "siguiente_trozo" if f["trozos_entre"] == 1 else "dos_o_mas"
        groups = {}
        for via in ("directa", "subasta"):
            rows = [r for r in fl if way(r) == via]
            kinds = Counter(kind(r) for r in rows)
            groups[via] = {"n": len(rows), "por_tipo": dict(kinds),
                           "con_actualizacion_por_subasta": sum(1 for r in rows if r["flash"].get("actualizacion_por_subasta")),
                           "bono_usd": {k: sum(r["bono_usd"] for r in rows if kind(r) == k) for k in kinds},
                           "reaccion_ms": quantiles([r["flash"]["reaccion_ms"] for r in rows if "reaccion_ms" in r["flash"]]),
                           "t_liquidacion_ms": quantiles([r["flash"]["t_liquidacion_ms"] for r in rows if "t_liquidacion_ms" in r["flash"]])}
        out["flash"] = {"n": len(fl), "grupos": groups, "watcher": meta.get("flashblocks")}
    if meta.get("via_rapida") or meta.get("flash_ws"):
        wins = [r["flash"]["ws_ventana_ms"] for r in liqs if (r.get("flash") or {}).get("ws_ventana_ms") is not None]
        out["via_rapida"] = {"resumen": meta.get("via_rapida"), "ws": meta.get("flash_ws"), "cruces": rapido or [],
                             "ventana_ws_ms": quantiles(wins)}
    clased = []
    for r in liqs:
        f = r.get("flash") or {}
        k = clasificar(f.get("propinas"))
        if k:
            clased.append({"clase": k, "bono_usd": r["bono_usd"], "etiqueta": r["etiqueta"], "trozos_entre": f.get("trozos_entre"),
                           "gap_tx": (f.get("propinas") or {}).get("gap")})
    if clased:
        out["clases_en_vivo"] = clased
    if perfiles:
        out["flash_perfil"] = flash_profile(perfiles, {b["bloque"]: b["n_tx"] for b in bloques if b.get("n_tx")})
    if cruces is not None or meta.get("flash_evaluador"):
        fc = cruces or []
        liquidated = [r for r in fc if r.get("resultado") == "liquidada"]
        with_slack = [r for r in liquidated if r.get("holgura_ms") is not None]
        out["flash_cruces"] = {
            "n": len(fc), "go": sum(1 for r in fc if r.get("decision") == "GO"),
            "resultados": dict(Counter(r.get("resultado") for r in fc)),
            "decision_ms": quantiles([r["decision_ms"] for r in fc if r.get("decision_ms") is not None]),
            "mismo_trozo": sum(1 for r in liquidated if r.get("mismo_trozo")),
            "holgura": {"n": len(with_slack), "positivas": sum(1 for r in with_slack if r["holgura_ms"] > 0),
                        "ms": quantiles([r["holgura_ms"] for r in with_slack]),
                        "bono_usd": sum(r["bono_usd"] for r in with_slack), "bono_positivo_usd": sum(r["bono_usd"] for r in with_slack if r["holgura_ms"] > 0)},
            "liquidaciones_sin_cruce_visto": sum(1 for r in liqs if "flash_cruce" in r and r["flash_cruce"] is None),
            "evaluador": meta.get("flash_evaluador")}
    dropped = [r for r in liqs if r.get("resultado") == "liquidada" and r.get("decision") != "GO" and way(r) == "directa"
               and r["bono_usd"] >= cfg["min_bonus_usd"]]
    dropped.sort(key=lambda r: -r["bono_usd"])
    out["descartadas_que_pasaron"] = [{"mercado": r["etiqueta"], "razon": r.get("razon"), "bono_usd": r["bono_usd"],
                                       "delta_bloques": r.get("delta_bloques"), "tx": r["tx"]} for r in dropped[:10]]
    closures = Counter(r["resultado"] for r in resultados if r.get("resultado") in
                       ("recuperada", "expirada", "invalidada_por_reorg", "perdida_por_salto", "abierta_al_cierre"))
    out["candidatas_sin_liquidar"] = dict(closures)

    c = meta.get("contadores") or {}
    events = Counter(s.get("evento") for s in sistema)
    out["calidad"] = {"contadores": c, "eventos_del_sistema": dict(events), "multicall_ok": meta.get("multicall_ok"),
                      "libro": meta.get("libro"), "libro_deriva": meta.get("libro_deriva"), "pendientes_al_cierre": meta.get("pendientes"),
                      "inicio": meta.get("inicio"), "fin": meta.get("fin"), "supuestos": meta.get("supuestos"), "bloom": meta.get("bloom"),
                      "mercados": len(meta.get("mercados") or {}), "excluidos": meta.get("mercados_excluidos")}
    last = cercanas[-1] if cercanas else None
    if last:
        top = last.get("top") or []
        out["cercanas"] = {"bloque": last["bloque"], "n": len(top), "deuda_usd": sum(t.get("deuda_usd") or 0 for t in top),
                           "mas_cercana_pct": min((t["caida_de_precio_pct"] for t in top if t.get("caida_de_precio_pct") is not None), default=None),
                           "fotos": len(cercanas)}
    return out


def rpc_methods(*metas):
    """Todos los métodos de RPC que usó cualquiera de las corridas."""
    used = set()
    for meta in metas:
        for prov in ((meta or {}).get("rpc") or {}).values():
            for m in (prov.get("metodos") or {}):
                used.add(m.split("@")[0])
    return used


# --- Puertas ----------------------------------------------------------------------------
def gate(nombre, estado, evidencia):
    return {"puerta": nombre, "estado": estado, "evidencia": evidencia}


def gates(live, replay, methods):
    """Las puertas del cap. 6 del Omega para la fase Shadow y el criterio de salida del cap. 5."""
    G = []
    c = (live or {}).get("calidad", {}).get("contadores", {}) if live else {}
    go = (live or {}).get("go") if live else None

    # Criterio de salida: decisiones en tiempo real sin enviar nada
    if not methods:
        G.append(gate("Decisiones en tiempo real sin enviar nada", "sin_datos", "no hay informe de llamadas RPC"))
    else:
        bad = sorted(m for m in methods if m.startswith(DANGEROUS_PREFIXES))
        odd = sorted(m for m in methods if m not in READ_ONLY and m not in bad)
        if bad:
            G.append(gate("Decisiones en tiempo real sin enviar nada", "falla", "métodos peligrosos: " + ", ".join(bad)))
        elif odd:
            G.append(gate("Decisiones en tiempo real sin enviar nada", "parcial", "métodos fuera de la lista de lectura: " + ", ".join(odd)))
        elif live and live["decisiones"]["por_decision"]:
            n = sum(live["decisiones"]["por_decision"].values())
            G.append(gate("Decisiones en tiempo real sin enviar nada", "cumple",
                          f"{n} decisiones; solo métodos de lectura ({len(methods)} distintos)"))
        else:
            G.append(gate("Decisiones en tiempo real sin enviar nada", "parcial", "solo métodos de lectura, pero ninguna decisión en la ventana"))

    # Criterio de salida: cada GO contra lo que ocurrió
    if go is None or go["n"] == 0:
        G.append(gate("Cada GO comparado con lo que ocurrió", "sin_datos", "ningún GO en la ventana en vivo"))
    else:
        open_ = go["n"] - go["cerrados"]
        certain = go["n"] - go.get("con_cruce_incierto", 0)          # los de cruce incierto (ya liquidables al arrancar) no miden una carrera
        G.append(gate("Cada GO comparado con lo que ocurrió", "cumple" if open_ == 0 and certain > 0 else "parcial",
                      f"{go['cerrados']} de {go['n']} GO con desenlace conocido ({', '.join(f'{k} {v}' for k, v in sorted(go['destino'].items()))})"
                      + ("" if certain else "; todos con cruce incierto (ya eran liquidables al arrancar): no miden una carrera")))

    # Reorganizaciones
    if not live:
        G.append(gate("Control de reorganizaciones", "sin_datos", "sin corrida en vivo"))
    else:
        reorgs, jumps, lost = c.get("reorgs", 0), c.get("saltos", 0), c.get("bloques_perdidos", 0)
        pending_lost = c.get("bloques_perdidos", 0) - c.get("bloques_recuperados", 0) - c.get("bloques_perdidos_definitivos", 0)
        G.append(gate("Control de reorganizaciones", "falla" if c.get("bloques_perdidos_definitivos") else "parcial",
                      f"{reorgs} reorgs vistos, {jumps} saltos de atraso ({c.get('bloques_saltados', 0)} bloques cubiertos con eventos), "
                      f"{lost} bloques perdidos ({c.get('bloques_recuperados', 0)} recuperados, {max(0, pending_lost)} sin recuperar, "
                      f"{c.get('bloques_perdidos_definitivos', 0)} definitivos); la recuperación se prueba con una cadena falsa"))

    # Simulaciones: divergencias
    div = []
    if live:
        for k in ("deriva_por_eventos", "deriva_en_critico", "deriva_reconciliacion"):
            if c.get(k):
                div.append(f"{k} {c[k]}")
        if live["liquidaciones"]["clases"].get("fuera_del_libro"):
            div.append(f"fuera_del_libro {live['liquidaciones']['clases']['fuera_del_libro']}")
    p = (replay or {}).get("paridad") if replay else None
    if p and p["n"] and p["dentro_1e6"] < p["n"]:
        div.append(f"paridad: {p['n'] - p['dentro_1e6']} de {p['n']} con error > 1e-6 (máx {p['max']:.2e})")
    if not live and not p:
        G.append(gate("Simulaciones: divergencias investigadas", "sin_datos", "sin libro en vivo ni paridad del replay"))
    elif div:
        G.append(gate("Simulaciones: divergencias investigadas", "falla", "hay que investigar: " + "; ".join(div)))
    else:
        parts = []
        if p and p["n"]:
            parts.append(f"paridad {p['exactas']}/{p['n']} exacta, máx {p['max']:.1e}")
        if live:
            parts.append(f"libro sin deriva ({c.get('reconciliadas', 0)} posiciones reconciliadas)")
        enough = bool(p and p["n"] >= 20) and bool(live)
        G.append(gate("Simulaciones: divergencias investigadas", "cumple" if enough else "parcial", "; ".join(parts)))

    # Latencia
    lat = (live or {}).get("latencia") if live else None
    if not lat or not lat["visto_ms"]["n"]:
        G.append(gate("Latencia en infraestructura real", "sin_datos", "sin bloques con latencia medida"))
    else:
        t = lat["visto_mas_proceso_ms"]
        G.append(gate("Latencia en infraestructura real", "parcial",
                      f"p50 {num(t['p50'])} ms, p90 {num(t['p90'])} ms, p99 {num(t['p99'])} ms (n={t['n']}); medida desde GitHub Actions, no desde la infraestructura de Titan"))

    # Detección competitiva
    if not replay:
        G.append(gate("Detección competitiva (replay)", "sin_datos", "este reporte no incluye un replay"))
    elif not replay["ganables"]["elegibles"]:
        G.append(gate("Detección competitiva (replay)", "sin_datos", "el replay no produjo liquidaciones directas elegibles"))
    else:
        g = replay["ganables"]
        G.append(gate("Detección competitiva (replay)", "parcial",
                      f"{g['elegibles']} liquidaciones directas elegibles reconstruidas; versión mínima del túnel (cruce → liquidación), no reproduce NQC completo"))

    # Economía
    if not replay:
        G.append(gate("Economía con costos completos", "sin_datos", "este reporte no incluye un replay"))
    elif not replay["ganables"]["elegibles"]:
        G.append(gate("Economía con costos completos", "sin_datos", "sin liquidaciones elegibles"))
    else:
        G.append(gate("Economía con costos completos", "parcial",
                      "bono × retención observada en el Census (incluye swap, gas y propinas de los ganadores reales); no se simuló nuestra ruta ni su liquidez"))
    return G


NOT_PROVEN = (
    "La latencia se mide desde un servidor de GitHub Actions hacia RPC públicos. La infraestructura real (nodo propio, cercanía al "
    "secuenciador de Base, Titan) puede ser mejor o peor: es una referencia conservadora, no una certificación.",
    "No se envió nada, así que no se midió el envío (se supone 150 ms), ni la inclusión, ni el orden dentro del bloque.",
    "Un empate (llegar en el mismo bloque que el ganador) lo decide la propina y el orden del secuenciador: aquí solo se cuenta.",
    "Los bloques de Base son de 2 s y el timestamp es entero. Con Flashblocks (200 ms) algunos bots ven antes del bloque: las liquidaciones "
    "en el mismo bloque del cruce no se pueden ganar sin ver antes de que el bloque cierre.",
    "El replay solo ve posiciones que terminaron liquidadas; las que se recuperaron o quedaron sin liquidar las mide el modo en vivo.",
    "El neto usa la retención observada del Census (bono × proporción que se quedaron los ganadores); no es una ejecución simulada con nuestra "
    "ruta, liquidez, flash loan ni slippage.",
    "El gas y la propina del replay son los de quien ganó, no los nuestros.",
    "Una ventana corta no sustituye semanas de Shadow ni cubre los picos: en el Census el 95% del margen cayó en 3 de 30 días.",
)


# --- Armado -----------------------------------------------------------------------------
def replay_thresholds(cfg):
    """Umbrales de bono y de neto con los que se lee el replay: los suyos (replay_*) o, si no los hay, los generales."""
    return {"min_bonus_usd": cfg.get("replay_min_bonus_usd", cfg["min_bonus_usd"]),
            "min_net_usd": cfg.get("replay_min_net_usd", cfg["min_net_usd"])}


def build(live_dir=None, replay_dir=None, cfg=None, diag_dir=None):
    """Junta el vivo, el replay y la lupa del oráculo; cada parte puede venir de una corrida distinta.
    La lupa (diag.jsonl, diag_oraculos.json) se lee de `diag_dir`, o del replay si no se indica."""
    cfg = {"min_bonus_usd": DEFAULTS["min_bonus_usd"], "min_net_usd": DEFAULTS["min_net_usd"], **(cfg or {})}
    res = {"generado": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()), "config": cfg, "fuentes": {},
           "supuestos": {"priors": SHADOW_PRIORS_SOURCE, "submit_ms": cfg.get("submit_ms", DEFAULTS["submit_ms"]),
                         "bloque_ms": BLOCK_MS}}
    live = replay = live_meta = replay_meta = None
    weights = None
    if live_dir and os.path.isdir(live_dir):
        b, bad1 = read_jsonl(os.path.join(live_dir, "bloques.jsonl"))
        d, bad2 = read_jsonl(os.path.join(live_dir, "decisiones.jsonl"))
        r, bad3 = read_jsonl(os.path.join(live_dir, "resultados.jsonl"))
        s, bad4 = read_jsonl(os.path.join(live_dir, "eventos_del_sistema.jsonl"))
        cc, bad5 = read_jsonl(os.path.join(live_dir, "cercanas.jsonl"))
        live_meta = read_json(os.path.join(live_dir, "meta.json"))
        res["fuentes"]["vivo"] = {"bloques": len(b), "decisiones": len(d), "resultados": len(r), "lineas_cortadas": bad1 + bad2 + bad3 + bad4 + bad5,
                                  "meta": live_meta is not None}
        crs, bad6 = read_jsonl(os.path.join(live_dir, "flash_cruces.jsonl"))
        cruces = crs if (crs or os.path.exists(os.path.join(live_dir, "flash_cruces.jsonl"))) else None
        perfiles, bad7 = read_jsonl(os.path.join(live_dir, "flash_bloques.jsonl"))
        rapido, bad9 = read_jsonl(os.path.join(live_dir, "flash_rapido.jsonl"))
        res["fuentes"]["vivo"]["lineas_cortadas"] += bad6 + bad7 + bad9
        if b or d or r or live_meta:
            live = analyze_live(b, d, r, s, cc, live_meta, cfg, cruces, perfiles, rapido)
            muestras, bad8 = read_jsonl(os.path.join(live_dir, "orden_bloques.jsonl"))
            res["fuentes"]["vivo"]["lineas_cortadas"] += bad8
            if muestras:
                live["orden"] = analyze_order(muestras, perfiles)
                live["prueba_clasificador"] = validate_classifier(muestras, perfiles, {x["bloque"]: x.get("n_tx") for x in b})
    if replay_dir and os.path.isdir(replay_dir):
        rows, bad1 = read_jsonl(os.path.join(replay_dir, "replay.jsonl"))
        errs, bad2 = read_jsonl(os.path.join(replay_dir, "replay_errores.jsonl"))
        replay_meta = read_json(os.path.join(replay_dir, "replay_meta.json"))
        weights = {(r.get("tx"), r.get("mercado"), r.get("prestatario")): weight(r) for r in rows}
        res["fuentes"]["replay"] = {"filas": len(rows), "errores": len(errs), "lineas_cortadas": bad1 + bad2, "meta": replay_meta is not None}
        if rows or replay_meta:
            # El replay puede tener su propio umbral (el vivo puede usar uno más bajo para juntar más GO que comparar).
            replay = analyze_replay(rows, errs, replay_meta, {**cfg, **replay_thresholds(cfg)})
    res["vivo"], res["replay"] = live, replay
    res["orden_historico"] = None
    if replay_dir and os.path.isdir(replay_dir):
        historicos, _ = read_jsonl(os.path.join(replay_dir, "orden_bloques.jsonl"))
        if historicos:
            res["orden_historico"] = analyze_order(historicos)
    res["diagnostico"] = None
    diag_dir = diag_dir or replay_dir
    if diag_dir and os.path.isdir(diag_dir):
        drows, _ = read_jsonl(os.path.join(diag_dir, "diag.jsonl"))
        if drows:
            res["diagnostico"] = analyze_diag(drows, read_json(os.path.join(diag_dir, "diag_oraculos.json")), weights)
            res["fuentes"]["lupa"] = {"filas": len(drows)}
    res["metodos_rpc"] = sorted(rpc_methods(live_meta, replay_meta))
    res["puertas"] = gates(live, replay, set(res["metodos_rpc"]))
    res["no_prueba"] = list(NOT_PROVEN)
    return res


# --- Escritura --------------------------------------------------------------------------
def table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return out


def ms(x):
    return "—" if x is None else f"{x:,.0f} ms"


def cell(g, k_total=None):
    """Una celda "n · $": cuántas liquidaciones y cuánto bono (estimado a toda la ventana)."""
    return f"{pct(g['parte_n'])} · {usd(g['bono_est_usd'])}"


ESTADO = {"cumple": "✅ cumple", "parcial": "🟡 parcial", "sin_datos": "⚪ sin datos", "falla": "❌ falla"}


def via_rapida_lines(vr):
    """Texto de la vía rápida: trozos por WebSocket y precio del oráculo calculado en casa."""
    L = []
    r, ws = vr.get("resumen") or {}, vr.get("ws") or {}
    if ws:
        subs = ", ".join(f"{k} {v}" for k, v in sorted((ws.get("suscripciones") or {}).items())) or "ninguna"
        L.append(f"- WebSocket ({ws.get('url')}): suscripciones {subs}; {num(ws.get('transacciones', 0))} transacciones y {num(ws.get('logs', 0))} logs "
                 f"recibidos; {ws.get('conexiones', 0)} conexiones" + (f"; errores {ws['errores']}" if ws.get("errores") else "") +
                 (f"; silencio entre trozos p50 {ms((ws.get('silencio_entre_trozos_ms') or {}).get('p50'))}" if (ws.get("silencio_entre_trozos_ms") or {}).get("n") else "") + ".")
    if r:
        d, v = r.get("decision_ms") or {}, r.get("ventaja_frente_a_la_consulta_ms") or {}
        L.append(f"- Vía rápida (precio del oráculo calculado en casa al llegar su actualización): {num(r.get('actualizaciones', 0))} actualizaciones; decidir "
                 f"tomó p50 {ms(d.get('p50'))} (p90 {ms(d.get('p90'))}) desde que llegó la actualización, sin consultar a la red"
                 + (f"; el WebSocket trajo la actualización {ms(v.get('p50'))} antes que la consulta del bloque pendiente (p50, n={v['n']})" if v.get("n") else "")
                 + f"; {r.get('cruces', 0)} cruces vistos así, {r.get('cruces_liquidados', 0)} liquidados.")
        h = r.get("holgura_ms") or {}
        if h.get("n"):
            L.append(f"- Holgura de la vía rápida frente al ganador (envío supuesto de {r.get('supuesto_envio_ms')} ms): positiva en {r.get('holgura_positiva')} "
                     f"de {h['n']}; mediana {ms(h.get('p50'))}.")
    w = vr.get("ventana_ws_ms") or {}
    if w.get("n"):
        L.append(f"- Ventana medida por WebSocket entre la actualización del oráculo y la liquidación del ganador: mediana {ms(w['p50'])}, "
                 f"mín {ms(w['min'])}, máx {ms(w['max'])} (n={w['n']}). Es el tiempo que hubo para ver, decidir y enviar.")
    return L


def separation_lines(sp):
    """Texto de la separación entre la actualización del oráculo y la liquidación (ver `separation`)."""
    t = sp["todas"]

    def how(x):
        s = f"mediana {x['tx']['p50']:g} transacciones, p90 {x['tx']['p90']:g}"
        if x["fraccion"]["n"]:
            s += f" (≈ {pct(x['fraccion']['p50'])} del bloque, unos {ms(x['ms_aprox']['p50'])}; p90 {ms(x['ms_aprox']['p90'])})"
        return s
    L = [f"Separación entre la actualización del oráculo y la liquidación, dentro del mismo bloque ({t['n']} casos): {how(t)}. "
         "Tramos: " + ", ".join(f"{k} {v}" for k, v in t["tramos"].items()) + "."]
    vias = {"subasta": "por la subasta OEV", "normal": "por un transmisor normal"}
    parts = [f"{vias[v]} {x['n']} (mediana {x['tx']['p50']:g} tx" + (f", unos {ms(x['ms_aprox']['p50'])}" if x["ms_aprox"]["n"] else "") + ")"
             for v, x in sp["por_via"].items()]
    if parts:
        L.append("Según cómo se actualizó el oráculo: " + "; ".join(parts) + ".")
    pp = sp.get("por_prioridad") or {}
    if any(x["n"] for x in pp.values()):
        names = {"mayor": "pagó más prioridad que la actualización", "igual": "pagó la misma", "menor": "pagó menos"}
        parts = [f"{names[k]}: {x['n']} casos, {pct(x['parte_del_bono'])} del bono" + (f" ({usd(x['bono_est_usd'])})" if sp.get("con_pesos") else "")
                 for k, x in pp.items() if x["n"]]
        L.append("Prioridad que pagó la liquidación frente a la de la actualización — " + "; ".join(parts) + ". Es una primera lectura: pagar más puede "
                 "ser un trozo posterior, pero también alguien que se coló tarde en el mismo trozo; la clasificación de abajo lo separa.")
    pc = sp.get("por_clase") or {}
    if any(x["n"] for x in pc.values()):
        short_names = {"trozo_siguiente": "en un trozo posterior (reaccionó al trozo publicado)",
                       "mismo_trozo": "colada en el mismo trozo, justo tras la actualización (vio la actualización antes de que se confirmara)",
                       "empaquetada": "empaquetada con la actualización (misma propina, subasta OEV)",
                       "ambigua": "ambigua (paga menos que la actualización)"}
        parts = [f"{short_names[k]}: {pc[k]['n']} casos, {pct(pc[k]['parte_del_bono'])} del bono" +
                 (f" ({usd(pc[k]['bono_est_usd'])})" if sp.get("con_pesos") else "") for k in short_names if pc[k]["n"]]
        L.append("**Clasificación por las propinas vecinas** (dentro de un trozo la propina baja; una que sube justo en la liquidación y vuelve al "
                 "nivel de antes es un pico que entró tarde al mismo trozo; una que está en la cabeza ordenada de otro trozo es una reacción): " +
                 "; ".join(parts) + ".")
    if t["fraccion"]["n"]:
        L.append("_Los milisegundos son una aproximación: suponen que las transacciones se reparten parejo en los 2 s del bloque; el sello exacto "
                 "de cada transacción solo se ve en vivo, por trozos de 200 ms._")
    return L


def headline(res):
    L = []
    rp, lv = res.get("replay"), res.get("vivo")
    if rp and rp["ganables"]["elegibles"]:
        g = rp["ganables"]
        first = g["por_tiempo_total"][0]
        small = ", muestra pequeña" if g["muestra_pequena"] else ""
        L.append(f"**Replay**: de unas {num(g['elegibles_est'])} liquidaciones directas con margen (muestra de {g['elegibles']}{small}), "
                 f"con un tiempo total de {first['tiempo_total']} llegaríamos antes en {pct(first['antes']['parte_n'])} de los casos "
                 f"({pct(first['antes']['parte_bono'])} del bono), empataríamos en {pct(first['empate']['parte_n'])} y llegaríamos tarde en "
                 f"{pct(first['tarde']['parte_n'])} ({pct(first['tarde']['parte_bono'])} del bono: liquidadas en el mismo bloque del cruce).")
        L.append(f"Bono directo ganable estimado ({first['tiempo_total']}): {usd(first['antes']['bono_est_usd'])} antes + "
                 f"{usd(first['empate']['bono_est_usd'])} en empate, de {usd(g['bono_est_usd'])} en la ventana "
                 f"(neto del modelo {usd(first['antes']['neto_est_usd'])} + {usd(first['empate']['neto_est_usd'])}).")
    elif rp:
        L.append("**Replay**: no produjo liquidaciones directas elegibles; ver cobertura abajo.")
    else:
        L.append("**Replay**: sin datos.")
    dg = res.get("diagnostico")
    sp_ = (dg or {}).get("separacion") or {}
    pc = sp_.get("por_clase") or {}
    pp = sp_.get("por_prioridad") or {}
    if dg and any(x["n"] for x in pc.values()):
        part = lambda k: f"{pct(pc[k]['parte_del_bono'])}" + (f" (≈ {usd(pc[k]['bono_est_usd'])})" if sp_.get("con_pesos") else "")   # noqa: E731
        L.append(f"**Quién gana dentro del bloque** (lupa de {dg['n']} liquidaciones directas): {part('trozo_siguiente')} del bono lo ganó quien reaccionó en un trozo "
                 f"posterior al de la actualización (se puede competir con velocidad y propina); {part('mismo_trozo')} quien se coló en el mismo trozo justo "
                 f"después de la actualización (vio la actualización antes de que se confirmara: otra clase de infraestructura); {part('empaquetada')} iba "
                 f"empaquetado con la actualización (subasta OEV: no hay carrera); {part('ambigua')} es ambiguo.")
    elif dg and any(x["n"] for x in pp.values()):
        part = lambda k: f"{pct(pp[k]['parte_del_bono'])}" + (f" (≈ {usd(pp[k]['bono_est_usd'])})" if dg["separacion"].get("con_pesos") else "")   # noqa: E731
        L.append(f"**Dentro del bloque** (lupa de {dg['n']} liquidaciones directas): {part('mayor')} del bono lo ganaron bots que pagaron más prioridad que "
                 f"la actualización del oráculo y cayeron en un trozo posterior (reaccionaron: se puede competir); {part('igual')} iba empaquetado con la "
                 f"actualización (misma prioridad: no hay carrera); {part('menor')} es ambiguo.")
    if lv:
        v, t = lv["ventana"], lv["latencia"]["visto_mas_proceso_ms"]
        go = lv["go"]
        L.append(f"**En vivo** ({v['horas']:.1f} h, {num(v['bloques'])} bloques): {sum(lv['decisiones']['por_decision'].values())} decisiones, "
                 f"{go['n']} GO, {lv['liquidaciones']['n']} liquidaciones reales; latencia visto+proceso p50 {ms(t['p50'])}, p90 {ms(t['p90'])}.")
    else:
        L.append("**En vivo**: sin datos.")
    counts = Counter(g["estado"] for g in res["puertas"])
    L.append("**Puertas del Omega (Shadow)**: " + ", ".join(f"{n} {ESTADO[k].split(' ', 1)[1]}" for k, n in
                                                           sorted(counts.items(), key=lambda kv: list(ESTADO).index(kv[0]))) + ".")
    return L


def render(res):
    L = [f"# Shadow Base/Morpho · {res['generado'][:10]}", "",
         "> Solo lectura de la cadena. No se firmó ni se envió nada. Lo medido y lo supuesto van separados; "
         "los $ del replay son estimados para todo el período a partir de una muestra ponderada.", "",
         "## Respuesta corta", ""]
    L += [f"- {x}" for x in headline(res)]
    rp, lv = res.get("replay"), res.get("vivo")

    L += ["", "## 1. Margen de tiempo (replay histórico)", ""]
    if not rp:
        L.append("Sin datos del replay.")
    else:
        m = rp["meta"]
        if m.get("eventos_en_ventana") is not None:
            cover = share(m.get("bono_elegido_usd") or 0, m.get("bono_elegible_usd"))
            L.append(f"Muestra: {num(m['procesados'])} reconstruidas de {num(m['elegibles'])} liquidaciones con bono ≥ mínimo "
                     f"({num(m['eventos_en_ventana'])} en total), que cubren {pct(cover)} del bono. "
                     f"Sin dato: {rp['sin_dato']}, censuradas (≥ ventana): {rp['censuradas']}, con error: {rp['errores']}, "
                     f"residuos de liquidaciones parciales: {rp['residuales']}"
                     f"{', omitidas por tiempo: ' + str(m['omitidos_por_tiempo']) if m.get('omitidos_por_tiempo') else ''}.")
        L += ["", "Bloques entre el cruce (primer bloque liquidable) y la liquidación:", ""]
        rows = [(b["etiqueta"], b["n_directa"], b["n_subasta"], usd(b["bono_directo_est_usd"]), pct(b["parte_del_bono_directo"]))
                for b in rp["por_distancia"]]
        L += table(["Distancia", "Directas", "Subasta", "Bono directo (est.)", "% del bono"], rows)
        g = rp["ganables"]
        th = replay_thresholds(res["config"])
        L += ["", f"**Si tu tiempo total** (visto + decisión + envío) es… Solo directas con bono ≥ {usd(th['min_bonus_usd'])} y "
                  f"neto ≥ {usd(th['min_net_usd'])}, sin deuda mala ({g['elegibles']} en la muestra):", ""]
        rows = [(t["tiempo_total"], cell(t["antes"]), cell(t["empate"]), cell(t["tarde"])) for t in g["por_tiempo_total"]]
        L += table(["Tiempo total", "Llegas antes", "Empate", "Llegas tarde"], rows)
        L += ["", "Cada celda: % de las liquidaciones · bono estimado. «Tarde» = alguien liquidó antes de que tu transacción pudiera caer."]
        if g["censuradas"]["n"]:
            L.append(f"Aparte: {g['censuradas']['n']} liquidaciones llevaban al menos la ventana completa liquidables ({usd(g['censuradas']['bono_est_usd'])}); "
                     "no se cuentan arriba porque no es una carrera.")
        vias = rp["vias"]
        L += ["", "Vía: " + ", ".join(f"{k} {v['n']} ({usd(v['bono_est_usd'])})" for k, v in sorted(vias.items())) +
              ". Las de subasta no son para un actor pequeño (el bono se cede en la puja)."]
        d = rp["distancia_directas"]
        if d["n"]:
            L.append(f"Distancia de las directas: mediana {d['p50']} bloques, p90 {d['p90']}, máx {d['max']}.")
        c = rp["costos_del_ganador"]
        if c["gas_usd"]["n"]:
            L.append(f"Costo de quien ganó (directas): gas mediano ${c['gas_usd']['p50']:.2f} (p90 ${c['gas_usd']['p90']:.2f}), "
                     f"propina mediana ${c['propina_usd']['p50']:.2f} (p90 ${c['propina_usd']['p90']:.2f}).")
        fb = rp.get("flashblocks")
        if fb:
            for url, r in fb.items():
                if url == "error":
                    L.append(f"Sonda de Flashblocks: {fb['error']}.")
                    continue
                iv = r.get("intervalo_entre_trozos_ms") or {}
                L.append(f"Sonda de Flashblocks ({short(url)}): {r.get('llamadas', 0)} consultas, latencia p50 {ms((r.get('rtt_ms') or {}).get('p50'))}; "
                         f"trozos nuevos del bloque pendiente: {r.get('trozos_nuevos_vistos', 0)}"
                         + (f", cada {ms(iv.get('p50'))} (p90 {ms(iv.get('p90'))})" if iv.get("n") else "")
                         + (f"; errores: {r['errores']}" if r.get("errores") else "") + ".")
        cl = rp.get("cobertura_libro")
        if cl:
            L.append("Cobertura del libro (prestatarios liquidados que un libro armado mirando N días atrás ya conocería, entre las "
                     "liquidaciones con esa historia disponible): " +
                     ", ".join(f"{x['dias']} d " + (f"{pct(x['parte_n'])} ({pct(x['parte_bono'])} del bono, n={x['n']})" if x["n"]
                                                   else "sin historia suficiente") for x in cl["por_dias_atras"]) + ".")
        gw, cd = rp.get("ganadores"), rp.get("concentracion_dias")
        if gw and gw["distintos"]:
            L.append(f"Quién se lleva el bono directo: {gw['distintos']} firmantes distintos en la muestra; el mayor {pct(gw['top1'])}, "
                     f"los 3 mayores {pct(gw['top3'])}, los 10 mayores {pct(gw['top10'])}.")
        if cd and cd["dias_con_liquidaciones"]:
            L.append(f"Cuándo cae: {cd['dias_con_liquidaciones']} días con liquidaciones directas; los 3 mejores días tienen {pct(cd['top3'])} del bono "
                     f"(el mejor, {pct(cd['top1'])}).")
        cc = rp["control_census"]
        if cc["razon"] is not None:
            L.append(f"Control contra el Census: bono directo estimado {usd(cc['bono_directo_replay_est_usd'])} vs {usd(cc['bono_directo_census_usd'])} "
                     f"del Census ({pct(cc['razon'])}).")
        if rp["por_mercado"]:
            L += ["", "Por mercado (directas):", ""]
            rows = [(m_["mercado"], m_["n_directa"], usd(m_["bono_directo_est_usd"]),
                     "—" if m_["mediana_bloques"] is None else f"{m_['mediana_bloques']:g}", pct(m_["parte_2_o_mas"]))
                    for m_ in rp["por_mercado"][:8]]
            L += table(["Mercado", "n", "Bono (est.)", "Mediana (bloques)", "≥ 2 bloques"], rows)

    dg = res.get("diagnostico")
    if dg:
        L += ["", "### Diagnóstico del oráculo (muestra de las liquidaciones directas más grandes)", ""]
        n = dg["n"]
        L.append(f"De {n} liquidaciones miradas bloque a bloque: la posición ya era liquidable un bloque antes en {dg['liquidable_un_bloque_antes']}; "
                 f"el precio de Morpho cambió en el mismo bloque de la liquidación en {dg['precio_cambio_en_el_bloque']}; "
                 f"algún feed del oráculo cambió de ronda en ese bloque en {dg['feed_cambio_en_el_bloque']}.")
        if dg["con_actualizacion_antes_en_el_bloque"]:
            L.append(f"En {dg['con_actualizacion_antes_en_el_bloque']} hubo una actualización del feed en el mismo bloque, antes de la liquidación "
                     f"(mediana {dg['tx_entre_actualizacion_y_liquidacion_mediana']:g} transacciones antes); quien actualizó fue el mismo actor "
                     f"que liquidó en {dg['mismo_actor']}.")
        sp = dg.get("separacion")
        if sp and sp["todas"]["n"]:
            L += ["", *separation_lines(sp)]
        oh = res.get("orden_historico")
        if oh and oh["bloques"]:
            L.append(f"Orden de propinas en {oh['bloques']} bloques llenos (mediana {num(oh['transacciones']['p50'])} transacciones): la propina sube de una "
                     f"transacción a la siguiente {num(oh['ascensos_por_bloque']['p50'])} veces por bloque (mediana; p90 {num(oh['ascensos_por_bloque']['p90'])}); "
                     f"con las mismas propinas en orden de llegada al azar subiría ≈ {num(oh['ascensos_si_fuera_al_azar']['p50'])} veces. "
                     "Un orden por prioridad dentro de cada trozo solo deja subidas al empezar cada trozo (~10) y las de transacciones que dependen de otra del mismo remitente.")
        for addr, feeds in list(dg["oraculos"].items())[:4]:
            L.append(f"- Oráculo {short(addr)}: " + ", ".join(f"{g} = {d[0] or '?'} ({short(d[1])})" for g, d in feeds.items()))
        if dg["errores"]:
            L.append(f"({dg['errores']} sin leer por errores de RPC.)")

    L += ["", "## 2. En vivo", ""]
    if not lv:
        L.append("Sin datos del modo en vivo.")
    else:
        v, lat = lv["ventana"], lv["latencia"]
        L.append(f"Ventana: {v['horas']:.2f} h, bloques {v['desde_bloque']}–{v['hasta_bloque']} "
                 f"({num(v['bloques'])} de {num(v['bloques_en_rango'])}, cobertura {pct(v['cobertura'])}).")
        L.append(f"Umbral para decidir GO en esta corrida: bono ≥ ${res['config']['min_bonus_usd']:g} y neto del modelo ≥ "
                 f"${res['config']['min_net_usd']:g} (el de operación sería ${DEFAULTS['min_bonus_usd']:g} y ${DEFAULTS['min_net_usd']:g}).")
        rows = [("Visto (desde el timestamp del bloque)", ms(lat["visto_ms"]["p50"]), ms(lat["visto_ms"]["p90"]), ms(lat["visto_ms"]["p99"]))]
        rows += [("Proceso (leer + decidir)", ms(lat["proceso_ms"]["p50"]), ms(lat["proceso_ms"]["p90"]), ms(lat["proceso_ms"]["p99"])),
                 ("Visto + proceso", ms(lat["visto_mas_proceso_ms"]["p50"]), ms(lat["visto_mas_proceso_ms"]["p90"]),
                  ms(lat["visto_mas_proceso_ms"]["p99"]))]
        L += ["", *table(["Latencia", "p50", "p90", "p99"], rows), "", "_" + lat["nota"] + "._"]
        ph = lat["fases_ms"]
        L.append("Dónde se va el tiempo (p50): " + ", ".join(f"{k.replace('_ms', '')} {ms(q['p50'])}" for k, q in ph.items()) + ".")
        cn_ = lv["calidad"]["contadores"]
        bl = (lv["calidad"].get("bloom") or {})
        if cn_.get("bloques_sin_logs_por_bloom") or bl:
            L.append(f"Logs: {num(cn_.get('bloques_sin_logs_por_bloom', 0))} de {num(v['bloques'])} bloques sin pedir logs porque el bloom del bloque "
                     f"descarta a Morpho (bloom {'verificado' if bl.get('ok') else 'no verificado'} con {bl.get('bloques_con_eventos', 0)} bloques con "
                     f"eventos; falsos negativos: {cn_.get('bloom_falsos_negativos', 0)}).")
        dec = lv["decisiones"]
        L += ["", "Decisiones: " + (", ".join(f"{k} {n}" for k, n in sorted(dec["por_razon"].items())) or "ninguna") + "."]
        go = lv["go"]
        if go["n"]:
            L.append(f"GO: {go['n']} (bono {usd(go['bono_usd'])}, neto del modelo {usd(go['neto_modelo_usd'])}). Desenlace: " +
                     ", ".join(f"{k} {n}" for k, n in sorted(go["destino"].items())) + ".")
            a = go["llegada_medida"]
            if any(x["n"] for x in a.values()):
                L.append("Los GO liquidados por otro, con la latencia medida: " +
                         ", ".join(f"{k} {x['n']} ({usd(x['bono_usd'])})" for k, x in a.items()) + ".")
            if go["con_cruce_incierto"]:
                L.append(f"{go['con_cruce_incierto']} GO tienen el cruce incierto (ya eran liquidables al arrancar o se detectaron tras un hueco); "
                         f"no cuentan en la llegada.")
            if go["liquidadas_por_subasta"]:
                L.append(f"⚠️ GO liquidados por la subasta: {go['liquidadas_por_subasta']}; el supuesto de «directa» falló.")
        lq = lv["liquidaciones"]
        if lq["n"]:
            L.append(f"Liquidaciones reales en la ventana: {lq['n']} (bono {usd(lq['bono_usd'])}). Clases: " +
                     ", ".join(f"{k} {n}" for k, n in sorted(lq["clases"].items())) + ". Vía: " +
                     ", ".join(f"{k} {n}" for k, n in sorted(lq["vias"].items())) + ".")
            if lq["recall_visibles"] is not None:
                L.append(f"Avisadas antes de ocurrir, de las que se podían ver: {pct(lq['recall_visibles'])}.")
            if lq["fuera_del_libro"]:
                L.append("⚠️ Liquidaciones de posiciones que el libro no tenía: " +
                         ", ".join(f"{x['mercado']} {usd(x['bono_usd'])}" for x in lq["fuera_del_libro"]) + ".")
        else:
            L.append("No hubo liquidaciones en los mercados vigilados durante la ventana (el Census ya mostró que se concentran en pocos días).")
        fb = lv.get("flash")
        if fb:
            w_ = fb.get("watcher") or {}
            L += ["", "Flashblocks (bloque pendiente de Base, trozos de ~200 ms):"]
            L.append(f"- Seguimiento cada {w_.get('intervalo_de_consulta_ms', '?')} ms, latencia p50 {ms((w_.get('rtt_ms') or {}).get('p50'))}, "
                     f"{num(w_.get('fotos', 0))} fotos; trozos nuevos cada {ms((w_.get('intervalo_entre_trozos_ms') or {}).get('p50'))} (mediana).")
            names = {"mismo_trozo": "en el mismo trozo que la actualización del oráculo", "siguiente_trozo": "en el siguiente trozo",
                     "dos_o_mas": "2 o más trozos después", "sin_actualizacion": "sin actualización localizada", "no_visto": "sin verse en el pendiente"}
            for via in ("directa", "subasta"):
                g = fb["grupos"][via]
                if not g["n"]:
                    continue
                parts = ", ".join(f"{names[k]} {n} ({usd(g['bono_usd'].get(k, 0))})" for k, n in sorted(g["por_tipo"].items()))
                r_ = g["reaccion_ms"]
                L.append(f"- {via.capitalize()}s medidas: {g['n']}: {parts}"
                         + (f"; en {g['con_actualizacion_por_subasta']} la actualización pasó por la subasta de oráculo (OEV)"
                            if g["con_actualizacion_por_subasta"] else "") + "." +
                         (f" Reacción tras la actualización: mediana {ms(r_['p50'])}, p90 {ms(r_['p90'])}." if r_["n"] else ""))
        fp = lv.get("flash_perfil")
        if fp and fp["completos"]:
            L.append(f"- Perfil de los bloques ({num(fp['completos'])} vistos desde el principio): mediana {num(fp['txs_por_bloque']['p50'])} transacciones "
                     f"por bloque en {fp['trozos_por_bloque']['p50']:g} trozos (≈ {num(fp['txs_por_trozo']['p50'])} por trozo); parte del bloque "
                     "acumulada al terminar cada trozo (mediana): " + ", ".join(pct(x) for x in fp["fraccion_acumulada_p50"]) + "."
                     + ("" if fp["ultimo_trozo_completo"] is None else
                        f" El último trozo observado ya traía todo el bloque en {pct(fp['ultimo_trozo_completo'])} de los casos."))
        od = lv.get("orden")
        if od and od["con_perfil"]:
            def share_of(d_):
                tot_ = sum(d_.values())
                return (lambda k: pct(d_[k] / tot_)) if tot_ else (lambda k: "—")
            din, fro = share_of(od["dentro"]), share_of(od["frontera"])
            L.append(f"- Orden dentro del bloque comprobado en {od['con_perfil']} bloques sellados con trozos conocidos: dentro de un trozo la propina baja en "
                     f"{din('baja')}, queda igual en {din('igual')} y sube en {din('sube')} de los pares consecutivos; al empezar un trozo nuevo sube en "
                     f"{fro('sube')} de {sum(od['frontera'].values())} fronteras. Un orden por prioridad casi no tiene ascensos dentro del trozo.")
        vr = lv.get("via_rapida")
        if vr:
            L += via_rapida_lines(vr)
        pv = lv.get("prueba_clasificador")
        if pv and pv["bloques"]:
            rate = lambda x: pct(x["bien"] / x["n"]) if x["n"] else "—"                  # noqa: E731
            L.append(f"- Prueba del clasificador «mismo trozo / trozo posterior» con {pv['bloques']} bloques de trozos conocidos: reconoce el comienzo de un "
                     f"trozo en {rate(pv['fronteras'])} de {pv['fronteras']['n']} fronteras, un pico dentro del trozo en {rate(pv['picos'])} de {pv['picos']['n']} "
                     f"(el resto lo toma por un trozo nuevo), y la cabeza de un trozo nuevo como trozo posterior en {rate(pv['cabezas'])} de {pv['cabezas']['n']}.")
        fe = lv.get("flash_cruces")
        if fe:
            ev_ = fe.get("evaluador") or {}
            L.append(f"- Evaluador del estado pendiente: {fe['n']} cruces vistos antes de sellarse el bloque ({fe['go']} GO); decidimos "
                     f"{ms(fe['decision_ms']['p50'])} después de ver el trozo (p90 {ms(fe['decision_ms']['p90'])}); lectura del estado pendiente "
                     f"p50 {ms((ev_.get('lectura_pendiente_ms') or {}).get('p50'))}. Desenlace: "
                     + (", ".join(f"{k} {n}" for k, n in sorted(fe["resultados"].items())) or "ninguno") + ".")
            h = fe["holgura"]
            if h["n"]:
                L.append(f"- Holgura frente al ganador (nuestra transacción habría llegado {num(ev_.get('supuesto_envio_ms'))} ms después de decidir): "
                         f"positiva en {h['positivas']} de {h['n']} (bono {usd(h['bono_positivo_usd'])} de {usd(h['bono_usd'])}); "
                         f"mediana {ms(h['ms']['p50'])}; el ganador entró en el mismo trozo en que lo vimos en {fe['mismo_trozo']}.")
            if fe["liquidaciones_sin_cruce_visto"]:
                L.append(f"- {fe['liquidaciones_sin_cruce_visto']} liquidaciones reales no se vieron cruzar antes en el estado pendiente "
                         f"(el precio y la liquidación llegaron en el mismo trozo).")
        if lv["descartadas_que_pasaron"]:
            L += ["", "Directas que descartamos y alguien liquidó:", ""]
            L += table(["Mercado", "Razón del NO-GO", "Bono", "Bloques"],
                       [(x["mercado"], x["razon"], usd(x["bono_usd"]), x["delta_bloques"]) for x in lv["descartadas_que_pasaron"][:5]])
        if lv["candidatas_sin_liquidar"]:
            L.append("Candidatas que nadie liquidó: " + ", ".join(f"{k} {n}" for k, n in sorted(lv["candidatas_sin_liquidar"].items())) + ".")
        if lv.get("cercanas"):
            ce = lv["cercanas"]
            L.append(f"Última foto de posiciones cerca del umbral: {ce['n']} dentro del 2%, deuda {usd(ce['deuda_usd'])}"
                     f"{'' if ce['mas_cercana_pct'] is None else f', la más cercana a {ce['mas_cercana_pct']:.2f}% de caída'}.")

    L += ["", "## 3. ¿La matemática coincide con la cadena?", ""]
    p = rp["paridad"] if rp else None
    if p and p["n"]:
        L.append(f"Replay: {p['exactas']} de {p['n']} liquidaciones coinciden exactamente con la matemática de Morpho "
                 f"({p['dentro_1e9']} dentro de 1e-9; {p['con_interes']} incluyen interés acumulado). Error máximo {p['max']:.2e}, "
                 f"omitidas {sum(p['omitidas'].values())}.")
        for w in p["peores"][:3]:
            if w["error"] > 1e-9:
                L.append(f"- Peor: {short(w['tx'])} · {w['mercado']} · error {w['error']:.2e}")
    else:
        L.append("Sin comparación de paridad en esta corrida.")
    if lv:
        cn = lv["calidad"]["contadores"]
        L.append(f"Libro en vivo: {cn.get('reconciliadas', 0)} posiciones comparadas con la cadena, deriva por eventos {cn.get('deriva_por_eventos', 0)}, "
                 f"en el crítico {cn.get('deriva_en_critico', 0)}, por reconciliación {cn.get('deriva_reconciliacion', 0)}; "
                 f"reorgs {cn.get('reorgs', 0)}, saltos {cn.get('saltos', 0)}, bloques perdidos {cn.get('bloques_perdidos', 0)}.")

    L += ["", "## 4. Puertas del Omega para la fase Shadow", ""]
    L += table(["Puerta", "Estado", "Evidencia"], [(g["puerta"], ESTADO[g["estado"]], g["evidencia"]) for g in res["puertas"]])

    L += ["", "## 5. Qué NO prueba este Shadow", ""]
    L += [f"- {x}" for x in res["no_prueba"]]
    L += ["", "## Fuentes", "",
          f"- Priors: {res['supuestos']['priors']}.",
          f"- Envío supuesto: {res['supuestos']['submit_ms']} ms. Bloque: {res['supuestos']['bloque_ms']} ms.",
          f"- Archivos leídos: {json.dumps(res['fuentes'], ensure_ascii=False)}.",
          f"- Métodos RPC usados: {', '.join(res['metodos_rpc']) or '—'}."]
    return "\n".join(L) + "\n"


def write(res, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    md = render(res)
    with open(os.path.join(out_dir, "RESUMEN_SHADOW.md"), "w", encoding="utf-8") as fh:
        fh.write(md)
    with open(os.path.join(out_dir, "shadow.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1, default=lambda o: None if isinstance(o, float) and math.isnan(o) else str(o))
    return md
