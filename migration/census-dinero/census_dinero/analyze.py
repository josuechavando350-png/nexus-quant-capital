"""Agregación: saturación por mercado y reporte en español."""

import csv
import json
import os
import statistics
from collections import Counter, defaultdict

from .config import THRESHOLDS

SIZE_BUCKETS = [(0, 10), (10, 100), (100, 1_000), (1_000, 10_000), (10_000, float("inf"))]

LIQ_FIELDS = [
    "chain", "protocol", "market", "market_label", "block", "timestamp", "tx_hash", "log_index", "tx_index",
    "liquidator", "tx_from", "tx_to", "borrower", "collateral_symbol", "debt_symbol", "collateral_amount",
    "debt_amount", "debt_usd", "bonus_usd", "bonus_source", "lif", "gas_usd", "builder_usd", "net_usd",
    "builder_share", "builder_payment_complete", "direct_source", "realized_usd", "realized_complete",
    "third_party_usd", "native_source", "beneficiaries", "unpriced_tokens", "blocks_since_oracle", "seconds_since_oracle",
    "same_tx_as_oracle", "oracle_status", "liqs_in_tx", "enriched", "error",
]
MARKET_FIELDS = [
    "chain", "protocol", "market_label", "market", "liquidations", "valued", "bonus_usd", "net_usd", "gas_usd",
    "builder_usd", "realized_usd", "realized_median", "kept_share", "realized_coverage", "third_party_usd",
    "builder_share_median", "winners", "top_winner", "top_winner_share", "blocks_median",
    "same_block_pct", "seconds_median", "net_median", "state",
]


def load(paths):
    recs, metas = [], []
    for p in paths:
        with open(p) as fh:
            for line in fh:
                if line.strip():
                    recs.append(json.loads(line))
        meta_path = os.path.join(os.path.dirname(p), "meta.json")
        if os.path.exists(meta_path):
            with open(meta_path) as fh:
                metas.append(json.load(fh))
    return recs, metas


def label(r):
    cs, ds = r.get("collateral_symbol") or "?", r.get("debt_symbol") or "?"
    if r["protocol"] == "morpho":
        lltv = r.get("lltv")
        lltv_txt = f" lltv {lltv / 1e16:.1f}%" if isinstance(lltv, (int, float)) else ""
        return f"Morpho {cs}/{ds}{lltv_txt}"
    return f"{r.get('market', 'aave')} {cs}→{ds}"


def market_key(r):
    if r["protocol"] == "morpho":
        return (r["chain"], "morpho", r["market"])
    return (r["chain"], r.get("market", "aave"), f"{r.get('collateral')}|{r.get('debt')}")


def _median(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def _sum(xs):
    return sum(x for x in xs if x is not None)


def classify(m, th=THRESHOLDS):
    if m["liquidations"] < th.min_sample:
        return "muestra_insuficiente"
    bs = m["builder_share_median"]
    blocks = m["blocks_median"]
    if m["winners"] <= th.virgin_max_winners and (bs is None or bs < th.virgin_max_builder_share) \
            and (blocks is None or blocks >= th.virgin_min_blocks):
        return "virgen"
    margin = m.get("realized_median")
    if margin is None:
        margin = m.get("net_median")
    if m["winners"] >= th.dead_min_winners and (
            (bs is not None and bs >= th.dead_min_builder_share)
            or (blocks == 0 and bs is not None and bs >= th.dead_same_block_builder_share)
            or (margin is not None and margin <= 0)):
        return "muerta"
    return "disputada"


def winners_table(rs):
    by = defaultdict(float)
    for r in rs:
        if r.get("bonus_usd") is not None:
            by[r.get("liquidator")] += max(0.0, r["bonus_usd"])
    total = sum(by.values()) or 1.0
    return sorted(((w, v, v / total) for w, v in by.items()), key=lambda x: -x[1])


def summarize_group(rs):
    valued = [r for r in rs if r.get("bonus_usd") is not None]
    blocks = [r.get("blocks_since_oracle") for r in rs if r.get("blocks_since_oracle") is not None]
    wt = winners_table(rs)
    complete = [r for r in rs if r.get("builder_payment_complete") or r.get("direct_source") == "no_aplica_l2"]
    real = [r for r in rs if r.get("realized_complete") and r.get("realized_usd") is not None]
    real_bonus = _sum(r.get("bonus_usd") for r in real)
    return {
        "realized_usd": _sum(r["realized_usd"] for r in real),
        "realized_median": _median([r["realized_usd"] for r in real]),
        "realized_coverage": (len(real) / len(rs)) if rs else None,
        "kept_share": (_sum(r["realized_usd"] for r in real) / real_bonus) if real_bonus > 0 else None,
        "bonus_usd_measured": real_bonus,
        "third_party_usd": _sum(r.get("third_party_usd") for r in rs),
        "liquidations": len(rs),
        "valued": len(valued),
        "bonus_usd": _sum(r.get("bonus_usd") for r in rs),
        "net_usd": _sum(r.get("net_usd") for r in rs),
        "gas_usd": _sum(r.get("gas_usd") for r in rs),
        "builder_usd": _sum(r.get("builder_usd") for r in rs),
        "builder_share_median": _median([r.get("builder_share") for r in complete]),
        "winners": len({r.get("liquidator") for r in rs}),
        "top_winner": wt[0][0] if wt else None,
        "top_winner_share": wt[0][2] if wt else None,
        "blocks_median": _median(blocks),
        "same_block_pct": (sum(1 for b in blocks if b == 0) / len(blocks)) if blocks else None,
        "seconds_median": _median([r.get("seconds_since_oracle") for r in rs]),
        "net_median": _median([r.get("net_usd") for r in rs]),
        "builder_payment_coverage": (len(complete) / len(rs)) if rs else None,
    }


def analyze(recs, metas):
    for r in recs:
        r["market_label"] = label(r)
    markets = defaultdict(list)
    for r in recs:
        markets[market_key(r)].append(r)
    market_rows = []
    for key, rs in markets.items():
        m = summarize_group(rs)
        m.update({"chain": key[0], "protocol": rs[0]["protocol"], "market": rs[0].get("market"),
                  "market_label": rs[0]["market_label"]})
        m["state"] = classify(m)
        market_rows.append(m)
    market_rows.sort(key=lambda m: -(m["realized_usd"] if m["realized_coverage"] else (m["net_usd"] or 0)))

    by_cp = defaultdict(list)
    for r in recs:
        by_cp[(r["chain"], r["protocol"])].append(r)
    chain_rows = []
    for (c, p), rs in sorted(by_cp.items()):
        s = summarize_group(rs)
        s.update({"chain": c, "protocol": p})
        s["top3_share"] = sum(x[2] for x in winners_table(rs)[:3]) if rs else None
        chain_rows.append(s)

    sizes = []
    for lo, hi in SIZE_BUCKETS:
        rs = [r for r in recs if r.get("bonus_usd") is not None and lo <= r["bonus_usd"] < hi]
        s = summarize_group(rs) if rs else {"liquidations": 0}
        s.update({"lo": lo, "hi": hi})
        sizes.append(s)

    overall = summarize_group(recs) if recs else {}
    overall["top3_share"] = sum(x[2] for x in winners_table(recs)[:3]) if recs else None
    states = Counter(m["state"] for m in market_rows)
    entry = defaultdict(list)
    for r in recs:
        if r.get("tx_to"):
            entry[(r["chain"], r["tx_to"])].append(r)
    entrypoints = []
    for (c, to), rs in sorted(entry.items(), key=lambda kv: -len(kv[1]))[:12]:
        s_ = summarize_group(rs)
        entrypoints.append({"chain": c, "tx_to": to, "liquidations": len(rs), "senders": len({r.get("tx_from") for r in rs}),
                            "bonus_usd": s_["bonus_usd"], "kept_share": s_["kept_share"],
                            "third_party_usd": s_["third_party_usd"]})
    return {
        "entrypoints": entrypoints,
        "overall": overall,
        "by_chain_protocol": chain_rows,
        "markets": market_rows,
        "sizes": sizes,
        "states": dict(states),
        "winners_top": [{"liquidator": w, "bonus_usd": v, "share": s} for w, v, s in winners_table(recs)[:15]],
        "metas": metas,
    }


# --- Escritura ---------------------------------------------------------------------
def usd(x):
    if x is None:
        return "—"
    sign = "-" if x < 0 else ""
    x = abs(x)
    if x >= 1e6:
        return f"{sign}${x / 1e6:,.2f} M"
    if x >= 1e4:
        return f"{sign}${x / 1e3:,.1f} k"
    return f"{sign}${x:,.0f}"


def pct(x):
    return "—" if x is None else f"{100 * x:.0f}%"


def num(x, nd=0):
    return "—" if x is None else (f"{x:,.{nd}f}" if nd else f"{x:,.0f}")


def short(a):
    return (a[:6] + "…" + a[-4:]) if a and len(a) > 12 else (a or "—")


def render_md(res, title_date):
    o = res["overall"]
    metas = res["metas"]
    days = metas[0]["window"]["days"] if metas else "?"
    chains = ", ".join(sorted({m["chain"] for m in metas})) or "—"
    eth_rows = [c for c in res["by_chain_protocol"] if c["chain"] == "ethereum"]
    eth_bonus = sum(c["bonus_usd"] for c in eth_rows)
    eth_builder = sum(c["builder_usd"] for c in eth_rows)
    eth_cov = _median([c.get("builder_payment_coverage") for c in eth_rows])
    L = []
    L.append(f"# Census del dinero · {title_date}")
    L.append("")
    dtxt = f"{days:g} día" + ("" if days == 1 else "s") if isinstance(days, (int, float)) else f"{days} días"
    L.append(f"Ventana: **{dtxt}** · cadenas: {chains} · protocolos: Aave V3 y Morpho Blue.")
    L.append("")
    L.append("## Respuesta corta")
    L.append("")
    L.append(f"1. **¿Cuánto dinero hay?** Bono total pagado a liquidadores: **{usd(o.get('bonus_usd'))}** "
             f"en {num(o.get('liquidations'))} liquidaciones. Después de gas y pagos al builder les quedó "
             f"**{usd(o.get('net_usd'))}** (antes del costo de vender el colateral).")
    L.append(f"   **Lo que realmente se quedaron**, sumando todos los movimientos de tokens y ETH de cada "
             f"transacción (venta del colateral, flash loan, pujas a subastas de oráculo, builder y gas): "
             f"**{usd(o.get('realized_usd'))}**, el **{pct(o.get('kept_share'))}** del bono "
             f"(medido en {pct(o.get('realized_coverage'))} de las liquidaciones). Pagado en ETH a terceros "
             f"(subastas y builders): {usd(o.get('third_party_usd'))}.")
    L.append(f"2. **¿Quién se lo lleva?** {num(o.get('winners'))} liquidadores distintos; los 3 mayores se "
             f"llevan **{pct(o.get('top3_share'))}** del bono.")
    L.append(f"3. **¿En cuántos bloques?** Mediana de **{num(o.get('blocks_median'))} bloques** "
             f"({num(o.get('seconds_median'))} s) desde la última actualización del oráculo; "
             f"**{pct(o.get('same_block_pct'))}** ocurren en el mismo bloque.")
    if eth_rows:
        L.append(f"4. **¿Cuánto se queda el builder (Ethereum)?** **{pct(eth_builder / eth_bonus if eth_bonus else None)}** "
                 f"del bono en total (pago directo medido en {pct(eth_cov)} de las transacciones).")
    L.append("")
    L.append("## Por cadena y protocolo")
    L.append("")
    L.append("| Cadena | Protocolo | Liq. | Bono | Real | % quedó | A terceros | Ganadores | Top 3 | Bloques | Seg. |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for c in res["by_chain_protocol"]:
        L.append(f"| {c['chain']} | {c['protocol']} | {num(c['liquidations'])} | {usd(c['bonus_usd'])} | "
                 f"{usd(c['realized_usd'])} | {pct(c['kept_share'])} | {usd(c['third_party_usd'])} | "
                 f"{num(c['winners'])} | {pct(c.get('top3_share'))} | "
                 f"{num(c['blocks_median'])} | {num(c['seconds_median'])} |")
    L.append("")
    L.append("Real: lo que se quedaron los liquidadores en las transacciones con medición completa. "
             "Bloques y segundos: mediana desde la última actualización del oráculo involucrado.")
    L.append("")
    L.append("## Saturación de mercados")
    L.append("")
    st = res["states"]
    L.append(f"Vírgenes: **{st.get('virgen', 0)}** · disputados: **{st.get('disputada', 0)}** · "
             f"muertos: **{st.get('muerta', 0)}** · con muestra insuficiente (<{THRESHOLDS.min_sample}): "
             f"{st.get('muestra_insuficiente', 0)}.")
    L.append("")
    L.append("### Los 15 mercados que más dejaron a sus ganadores")
    L.append("")
    L.append("| Cadena | Mercado | Liq. | Bono | Real | % quedó | Ganadores | Top | Bloques | Estado |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---|")
    for m in res["markets"][:15]:
        L.append(f"| {m['chain']} | {m['market_label']} | {m['liquidations']} | {usd(m['bonus_usd'])} | "
                 f"{usd(m['realized_usd'])} | {pct(m['kept_share'])} | {m['winners']} | {pct(m['top_winner_share'])} | "
                 f"{num(m['blocks_median'])} | {m['state']} |")
    virgins = [m for m in res["markets"] if m["state"] == "virgen"]
    if virgins:
        L.append("")
        L.append("### Mercados vírgenes (un solo ganador, poca propina, sin carrera de bloque)")
        L.append("")
        for m in virgins[:20]:
            L.append(f"- {m['chain']} · {m['market_label']}: {m['liquidations']} liq., real {usd(m['realized_usd'])}, "
                     f"ganador {short(m['top_winner'])}")
    L.append("")
    L.append("## Por tamaño del bono")
    L.append("")
    L.append("| Bono | Liq. | Real total | Real mediano | % quedó | Ganadores |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for s in res["sizes"]:
        rng = f"{usd(s['lo'])}–{usd(s['hi'])}" if s["hi"] != float("inf") else f"≥ {usd(s['lo'])}"
        L.append(f"| {rng} | {num(s.get('liquidations'))} | {usd(s.get('realized_usd'))} | "
                 f"{usd(s.get('realized_median'))} | {pct(s.get('kept_share'))} | {num(s.get('winners'))} |")
    L.append("")
    L.append("## ¿Por dónde entran? (contrato llamado por la transacción)")
    L.append("")
    L.append("Si un mismo contrato recibe transacciones de muchos firmantes distintos y se queda con mucho en ETH, "
             "es una subasta o un enrutador compartido, no el bot de alguien.")
    L.append("")
    L.append("| Cadena | Contrato | Liq. | Firmantes | Bono | % quedó | A terceros |")
    L.append("|---|---|---:|---:|---:|---:|---:|")
    for e in res.get("entrypoints", []):
        L.append(f"| {e['chain']} | `{short(e['tx_to'])}` | {e['liquidations']} | {e['senders']} | {usd(e['bonus_usd'])} | "
                 f"{pct(e['kept_share'])} | {usd(e['third_party_usd'])} |")
    L.append("")
    L.append("## Ganadores principales")
    L.append("")
    for w in res["winners_top"][:10]:
        L.append(f"- `{w['liquidator']}` — {usd(w['bonus_usd'])} ({pct(w['share'])})")
    L.append("")
    L.append("## Cobertura de la medición")
    L.append("")
    L.append("| Cadena | Eventos | Valuados | Real completo | Con bloques de oráculo | Trazas de ETH | Precio | Tiempo agotado |")
    L.append("|---|---:|---:|---:|---:|---|---|---|")
    for m in metas:
        ps = m.get("price_sources", {})
        dp = m.get("native_trace_sources", m.get("direct_payment_sources", {}))
        L.append(f"| {m['chain']} | {m['events']} | {m['with_bonus_usd']} | {m.get('with_realized_complete', 0)} | "
                 f"{m['with_oracle_delta']} | "
                 f"{', '.join(f'{k}: {v}' for k, v in dp.items()) or '—'} | "
                 f"oráculo {ps.get('oraculo', 0)}, mercado {ps.get('defillama', 0)}, sin {ps.get('sin_precio', 0)} | "
                 f"{'sí' if m.get('time_budget_hit') else 'no'} |")
    L.append("")
    L.append("## Qué NO dice este census")
    L.append("")
    L.append("- \"Real\" es lo que se quedaron los ganadores actuales, no lo que ganaría NQC: para eso hay que "
             "ganarles la carrera o la subasta.")
    L.append("- Para medir \"Real\" se cuenta como del liquidador: el firmante, el contrato que llamó al protocolo y "
             "las cuentas sin código que solo reciben. Si un bot manda su ganancia a otro contrato propio, aquí se "
             "ve como pago a terceros y el \"Real\" sale menor.")
    L.append("- El bono está a precio de oráculo (o de mercado si no hubo nodo de archivo); \"Real\" ya incluye "
             "el deslizamiento de vender el colateral.")
    L.append("- En L2 no hay subasta de builders; la propina de prioridad sí se cuenta. Las pujas de Timeboost "
             "(Arbitrum) y la recaptura de Chainlink SVR (Aave en Ethereum) se pagan por fuera y no se ven aquí.")
    L.append("- No incluye pre-liquidaciones de Morpho ni otros protocolos (Spark, Compound, Euler, Fluid).")
    L.append("- Los umbrales de virgen / disputada / muerta son iniciales y se calibran con estos mismos datos.")
    L.append("")
    return "\n".join(L)


def write_outputs(res, recs, out_dir, title_date):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "liquidaciones.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=LIQ_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in sorted(recs, key=lambda r: (r["chain"], r["block"], r["log_index"])):
            w.writerow(r)
    with open(os.path.join(out_dir, "mercados.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=MARKET_FIELDS, extrasaction="ignore")
        w.writeheader()
        for m in res["markets"]:
            w.writerow(m)
    with open(os.path.join(out_dir, "resumen.json"), "w") as fh:
        json.dump({k: v for k, v in res.items() if k != "markets"} | {"markets_top50": res["markets"][:50]},
                  fh, indent=2, default=str)
    md = render_md(res, title_date)
    with open(os.path.join(out_dir, "RESUMEN.md"), "w") as fh:
        fh.write(md)
    return md
