"""Agregación: saturación por mercado, a dónde se va el bono y reporte en español."""

import csv
import json
import os
import statistics
from collections import Counter, defaultdict

from .config import KNOWN_SHARED_ENTRIES, THRESHOLDS

SIZE_BUCKETS = [(0, 10), (10, 100), (100, 1_000), (1_000, 10_000), (10_000, float("inf"))]

# Una liquidación "paga por el orden" (subasta de oráculo/OEV, builder o guerra de prioridad)
# si lo que sale en ETH a terceros más la propina de prioridad es al menos esta fracción del bono.
ORDER_PAID_SHARE = 0.30
# Margen mínimo, en USD por liquidación, que cuenta como "queda algo" para un actor pequeño.
SMALL_ACTOR_MIN_USD = (10, 100)

LIQ_FIELDS = [
    "chain", "protocol", "market", "market_label", "block", "timestamp", "tx_hash", "log_index", "tx_index",
    "liquidator", "tx_from", "tx_to", "borrower", "collateral_symbol", "debt_symbol", "collateral_amount",
    "debt_amount", "debt_usd", "bonus_usd", "bonus_source", "lif", "gas_usd", "priority_usd", "builder_usd",
    "net_usd", "builder_share", "builder_payment_complete", "direct_source", "realized_usd", "realized_complete",
    "third_party_usd", "oev_usd", "builder_direct_usd", "treasury_usd", "realized_raw_usd", "order_paid_usd", "route",
    "paid_over_bonus", "redeposit", "entry", "realized_base_usd",
    "realized_anomaly",
    "net_flows", "native_source",
    "beneficiaries", "unpriced_tokens",
    "blocks_since_oracle", "seconds_since_oracle", "same_tx_as_oracle", "oracle_in_tx", "oracle_status", "liqs_in_tx",
    "enriched", "error",
]
MARKET_FIELDS = [
    "chain", "protocol", "market_label", "market", "liquidations", "valued", "bonus_usd", "net_usd", "gas_usd",
    "builder_usd", "realized_usd", "realized_median", "kept_share", "realized_coverage", "third_party_usd",
    "builder_share_median", "winners", "top_winner", "top_winner_share", "blocks_median",
    "same_block_pct", "seconds_median", "net_median", "direct_liquidations", "direct_realized_usd", "state",
]
BOT_FIELDS = [
    "chain", "liquidator", "entrypoints", "signers", "liquidations", "bonus_usd", "realized_usd", "kept_share",
    "realized_median", "order_paid_usd", "blocks_median", "seconds_median", "markets", "days_active",
]


def load(paths):
    """Lee liquidaciones de uno o varios tramos; deduplica por (cadena, tx, log)."""
    recs, metas, seen = [], [], set()
    for p in paths:
        with open(p) as fh:
            for line in fh:
                if not line.strip():
                    continue
                r = json.loads(line)
                key = (r.get("chain"), r.get("tx_hash"), r.get("log_index"))
                if key in seen:
                    continue
                seen.add(key)
                recs.append(r)
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


def resolve_entries(recs):
    """Decide con todo el conjunto si el contrato llamado por la transacción es del bot o compartido.

    Compartido (subasta, enrutador): está en KNOWN_SHARED_ENTRIES o lo usan dos o más contratos
    liquidadores. Propio: lo usa un solo liquidador; entonces su saldo cuenta como del ganador y se
    usa la variante del neto que lo incluye en W."""
    users = defaultdict(set)
    for r in recs:
        to = r.get("tx_to")
        if to and to != r.get("liquidator"):
            users[(r["chain"], to)].add(r.get("liquidator"))
    for r in recs:
        alt = r.get("entry_variant")
        if not alt or r.get("tx_to") == r.get("pool"):
            # Sin entrada aparte, o la tx llama directo al protocolo (un EOA que liquida en Morpho).
            r["entry"] = "liquidador"
            continue
        key = (r["chain"], r.get("tx_to"))
        r["entry"] = "compartida" if key in KNOWN_SHARED_ENTRIES or len(users[key]) >= 2 else "propia"
        if r["entry"] != "propia" or r.get("_entry_applied"):
            continue
        r["_entry_applied"] = True
        r["realized_base_usd"] = r.get("realized_usd")
        r["realized_usd"] = alt.get("realized_usd")
        r["third_party_eth"] = alt.get("third_party_eth")
        eth = r.get("eth_usd")
        r["third_party_usd"] = alt["third_party_eth"] * eth if alt.get("third_party_eth") is not None and eth else None
        r["realized_complete"] = bool(alt.get("realized_complete"))
        r["net_flows"] = alt.get("net_flows")
        r["third_party_to"] = alt.get("third_party_to") or {}
        r["w_minimal"] = bool(alt.get("w_minimal"))
        r["w_extra"] = alt.get("w_extra") or []
        if alt.get("anomaly"):
            r["realized_anomaly"] = alt["anomaly"]
        else:
            r.pop("realized_anomaly", None)
    return recs


MEASURED_ROUTES = ("directa", "subasta")
ZERO = "0x" + "0" * 40


def sink_users(recs):
    """Liquidadores distintos que mandan valor a cada sumidero (contraparte que no devuelve nada)."""
    users = defaultdict(set)
    for r in recs:
        for a, c in (r.get("counterparties") or {}).items():
            if c[0] > 0 and c[1] == 0:
                users[(r["chain"], a)].add(r.get("liquidator"))
    return users


def sink_kind(r, a, users):
    if a == r.get("builder_coinbase"):
        return "builder"
    key = (r["chain"], a)
    if key in KNOWN_SHARED_ENTRIES or len(users.get(key, ())) >= 2:
        return "compartido"
    return "tesoreria"


def derive(r, users=None):
    """Campos derivados: propina, pagos por el orden (OEV y builder), tesorería del bot y ruta.

    Con `counterparties` (corridas nuevas) cada contraparte fuera de W se clasifica: si devuelve
    algo es un swap o préstamo (su costo queda en "resto"); si solo recibe, es el builder del bloque,
    una subasta compartida (≥ 2 liquidadores o conocida) o la tesorería del mismo bot, cuyo saldo
    cuenta como ganancia. Sin `counterparties` (corridas viejas) se usa solo el ETH a terceros."""
    eth = r.get("eth_usd")
    prio = (r.get("priority_eth") or 0) * eth if eth else None
    r["priority_usd"] = prio
    cps = r.get("counterparties")
    if cps is not None and not r.get("_attributed"):
        r["_attributed"] = True
        builder = oev = treasury = 0.0
        for a, (out, inn, _eth, _unpriced) in cps.items():
            if out <= 0 or inn > 0 or a == ZERO:
                continue
            kind = sink_kind(r, a, users or {})
            if kind == "builder":
                builder += out
            elif kind == "compartido":
                oev += out
            else:
                treasury += out
        r["builder_direct_usd"], r["oev_usd"], r["treasury_usd"] = builder, oev, treasury
        if r.get("realized_usd") is not None:
            r["realized_raw_usd"] = r["realized_usd"]
            r["realized_usd"] = r["realized_usd"] + treasury
        r["order_paid_usd"] = None if prio is None else builder + oev + prio
    elif cps is None:
        direct = (r.get("direct_eth") or 0) * eth if eth else None
        third = r.get("third_party_usd")
        r["order_paid_usd"] = None if third is None or prio is None else third + prio
        r["oev_usd"] = None if third is None or direct is None else max(0.0, third - direct)
        r["builder_direct_usd"] = None if third is None or r["oev_usd"] is None else third - r["oev_usd"]
    b, real = r.get("bonus_usd"), r.get("realized_usd")
    # Pagó por el orden mucho más que el bono: la tx probablemente incluye otra liquidación fuera
    # del alcance (otro protocolo) o arbitraje. Se marca; el bono medido es solo el de Aave/Morpho.
    r["paid_over_bonus"] = bool(b is not None and r.get("order_paid_usd") is not None
                                and r["order_paid_usd"] > max(1.5 * b, b + 20))
    gas = r.get("gas_usd") or 0
    if r.get("redeposit"):
        r["route"] = "refinanciacion"
    elif not r.get("realized_complete") or b is None or real is None or r.get("order_paid_usd") is None:
        r["route"] = "sin_medir"
    elif r["order_paid_usd"] >= max(ORDER_PAID_SHARE * b, 1.0):
        r["route"] = "subasta"
    elif b >= 20 and abs(real) <= gas + 1 and cps is not None:
        r["route"] = "sin_rastro"           # ni el ganador ni un sumidero se quedaron con el bono
    else:
        r["route"] = "directa"
    return r


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
    real = [r for r in rs if r.get("route") in MEASURED_ROUTES]
    real_bonus = _sum(r.get("bonus_usd") for r in real)
    direct = [r for r in real if r.get("route") == "directa"]
    return {
        "realized_usd": _sum(r["realized_usd"] for r in real),
        "realized_median": _median([r["realized_usd"] for r in real]),
        "realized_coverage": (len(real) / len(rs)) if rs else None,
        "kept_share": (_sum(r["realized_usd"] for r in real) / real_bonus) if real_bonus >= 1 else None,
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
        "oracle_coverage": (len(blocks) / len(rs)) if rs else None,
        "direct_liquidations": len(direct),
        "direct_realized_usd": _sum(r["realized_usd"] for r in direct),
    }


def _quantile(xs, q):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    return xs[min(len(xs) - 1, int(q * (len(xs) - 1) + 0.5))]


def money_flow(rs):
    """A dónde se va el bono, solo con liquidaciones de medición completa."""
    real = [r for r in rs if r.get("route") in MEASURED_ROUTES]
    bonus = _sum(r["bonus_usd"] for r in real)
    kept = _sum(r["realized_usd"] for r in real)
    prio = _sum(r.get("priority_usd") for r in real)
    gas_base = _sum((r.get("gas_usd") or 0) - (r.get("priority_usd") or 0) for r in real)
    oev = _sum(r.get("oev_usd") for r in real)
    direct = _sum(r.get("builder_direct_usd") for r in real)
    other = {k: (sum(1 for r in rs if r.get("route") == k), _sum(r.get("bonus_usd") for r in rs if r.get("route") == k))
             for k in ("sin_medir", "sin_rastro", "refinanciacion")}
    return {"n": len(real), "n_total": len(rs), "bonus": bonus, "kept": kept, "oev": oev, "builder_direct": direct,
            "priority": prio, "gas_base": gas_base, "rest": bonus - kept - prio - gas_base - oev - direct,
            "treasury": _sum(r.get("treasury_usd") for r in real), "other": other}


def payees(recs, top=15):
    """A quién va el ETH que sale del liquidador: subastas, builders o tesorerías del propio bot.

    Un destinatario que cobra de varios liquidadores distintos es una subasta o un builder; uno
    que solo cobra de un liquidador puede ser la tesorería del mismo bot (y entonces lo "pagado
    a terceros" sería ganancia)."""
    by = defaultdict(lambda: {"eth": 0.0, "usd": 0.0, "liquidators": set(), "n": 0, "coinbase": 0, "entry": 0})
    for r in recs:
        for a, eth in (r.get("third_party_to") or {}).items():
            d = by[(r["chain"], a)]
            d["eth"] += eth
            d["usd"] += eth * (r.get("eth_usd") or 0)
            d["liquidators"].add(r.get("liquidator"))
            d["n"] += 1
            d["coinbase"] += int(a == r.get("builder_coinbase"))
            d["entry"] += int(a == r.get("tx_to"))
    rows = []
    for (chain, a), d in by.items():
        kind = "builder" if d["coinbase"] >= d["n"] / 2 else (
            "compartido" if len(d["liquidators"]) >= 2 or (chain, a) in KNOWN_SHARED_ENTRIES else "un_solo_liquidador")
        rows.append({"chain": chain, "payee": a, "usd": d["usd"], "eth": d["eth"], "liquidations": d["n"],
                     "liquidators": len(d["liquidators"]), "kind": kind, "is_entry": d["entry"] > 0})
    rows.sort(key=lambda x: -x["usd"])
    return rows[:top]


def bots(recs, route="directa"):
    """Ganadores por (cadena, contrato liquidador) en liquidaciones de una ruta."""
    by = defaultdict(list)
    for r in recs:
        if r.get("route") == route:
            by[(r["chain"], r.get("liquidator"))].append(r)
    out = []
    for (chain, liq), rs in by.items():
        bonus = _sum(r["bonus_usd"] for r in rs)
        kept = _sum(r["realized_usd"] for r in rs)
        mk = Counter(r.get("market_label") or label(r) for r in rs)
        out.append({
            "chain": chain, "liquidator": liq,
            "entrypoints": len({r.get("tx_to") for r in rs}),
            "signers": len({r.get("tx_from") for r in rs}),
            "liquidations": len(rs), "bonus_usd": bonus, "realized_usd": kept,
            "kept_share": kept / bonus if bonus >= 1 else None,
            "realized_median": _median([r["realized_usd"] for r in rs]),
            "order_paid_usd": _sum(r.get("order_paid_usd") for r in rs),
            "blocks_median": _median([r.get("blocks_since_oracle") for r in rs]),
            "seconds_median": _median([r.get("seconds_since_oracle") for r in rs]),
            "markets": "; ".join(f"{m} ({n})" for m, n in mk.most_common(3)),
            "days_active": len({(r.get("timestamp") or 0) // 86400 for r in rs}),
        })
    out.sort(key=lambda b: -b["realized_usd"])
    return out


def small_actor(recs, chain_days):
    """¿Queda margen para un actor pequeño? Liquidaciones directas (sin pagar el orden) con neto real."""
    out = []
    for chain in sorted({r["chain"] for r in recs}):
        rs = [r for r in recs if r["chain"] == chain and r.get("route") == "directa"]
        row = {"chain": chain, "days": chain_days.get(chain), "direct": len(rs),
               "measured": sum(1 for r in recs if r["chain"] == chain and r.get("route") in MEASURED_ROUTES),
               "total": sum(1 for r in recs if r["chain"] == chain),
               "kept_usd": _sum(r["realized_usd"] for r in rs),
               "winners": len({r.get("liquidator") for r in rs}),
               "blocks_median": _median([r.get("blocks_since_oracle") for r in rs]),
               "late_pct": None}
        blocks = [r.get("blocks_since_oracle") for r in rs if r.get("blocks_since_oracle") is not None]
        if blocks:
            row["late_pct"] = sum(1 for b in blocks if b >= 2) / len(blocks)
        for m in SMALL_ACTOR_MIN_USD:
            big = [r for r in rs if r["realized_usd"] >= m]
            wt = winners_table(big)
            row[f"ge{m}"] = len(big)
            row[f"ge{m}_usd"] = _sum(r["realized_usd"] for r in big)
            row[f"ge{m}_top_share"] = wt[0][2] if wt else None
            row[f"ge{m}_winners"] = len({r.get("liquidator") for r in big})
        out.append(row)
    return out


def coverage(metas, expected=None):
    """Cobertura por cadena juntando tramos; marca los tramos que faltan."""
    by = defaultdict(list)
    for m in metas:
        by[m["chain"]].append(m)
    chains = list(by)
    if expected:
        chains = list(dict.fromkeys(list(expected.get("chains", [])) + chains))
    out = []
    for c in chains:
        ms = by.get(c, [])
        want = None
        if expected:
            t = expected.get("tramos", 1)
            want = int(t.get(c, 1) if isinstance(t, dict) else t)
        win = [m.get("window") or {} for m in ms]
        days = sum(w.get("days") or 0 for w in win)
        sum_ = lambda k: sum(m.get(k) or 0 for m in ms)  # noqa: E731
        native = Counter()
        prices = Counter()
        terrs = Counter()
        oracle_status = Counter()
        for m in ms:
            native.update(m.get("native_trace_sources") or m.get("direct_payment_sources") or {})
            prices.update(m.get("price_sources") or {})
            terrs.update(m.get("trace_errors") or {})
            oracle_status.update(m.get("oracle_status") or {})
        out.append({
            "chain": c, "tramos": len(ms), "tramos_esperados": want, "days": days,
            "events": sum_("events"), "transactions": sum_("transactions"), "enriched": sum_("enriched"),
            "with_bonus_usd": sum_("with_bonus_usd"), "with_realized_complete": sum_("with_realized_complete"),
            "with_oracle_delta": sum_("with_oracle_delta"),
            "events_complete": all(m.get("events_complete", True) for m in ms) and bool(ms),
            "budget_hit": sum(1 for m in ms if m.get("time_budget_hit")),
            "interrupted": sum(1 for m in ms if m.get("interrupted")),
            "native": dict(native), "prices": dict(prices), "trace_errors": dict(terrs.most_common(5)),
            "oracle_status": dict(oracle_status),
            "elapsed_max_s": max([m.get("elapsed_s") or 0 for m in ms] or [0]),
        })
    return out


def analyze(recs, metas, expected=None):
    resolve_entries(recs)
    users = sink_users(recs)
    for r in recs:
        r["market_label"] = label(r)
        derive(r, users)
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
        s.update({"chain": c, "protocol": p, "flow": money_flow(rs)})
        s["top3_share"] = sum(x[2] for x in winners_table(rs)[:3]) if rs else None
        s["blocks_p25"] = _quantile([r.get("blocks_since_oracle") for r in rs], 0.25)
        s["blocks_p75"] = _quantile([r.get("blocks_since_oracle") for r in rs], 0.75)
        chain_rows.append(s)

    routes = []
    by_route = defaultdict(list)
    for r in recs:
        by_route[(r["chain"], r["route"])].append(r)
    for (c, route), rs in sorted(by_route.items()):
        s = summarize_group(rs)
        s.update({"chain": c, "route": route})
        routes.append(s)

    sizes = []
    for lo, hi in SIZE_BUCKETS:
        rs = [r for r in recs if r.get("bonus_usd") is not None and lo <= r["bonus_usd"] < hi]
        s = summarize_group(rs) if rs else {"liquidations": 0}
        s.update({"lo": lo, "hi": hi})
        sizes.append(s)

    overall = summarize_group(recs) if recs else {}
    overall["top3_share"] = sum(x[2] for x in winners_table(recs)[:3]) if recs else None
    overall["flow"] = money_flow(recs)
    states = Counter(m["state"] for m in market_rows)
    entry = defaultdict(list)
    for r in recs:
        if r.get("tx_to"):
            entry[(r["chain"], r["tx_to"])].append(r)
    entrypoints = []
    for (c, to), rs in sorted(entry.items(), key=lambda kv: -len(kv[1]))[:15]:
        s_ = summarize_group(rs)
        entrypoints.append({"chain": c, "tx_to": to, "liquidations": len(rs), "senders": len({r.get("tx_from") for r in rs}),
                            "bonus_usd": s_["bonus_usd"], "kept_share": s_["kept_share"],
                            "third_party_usd": s_["third_party_usd"],
                            "auction_pct": (sum(1 for r in rs if r["route"] == "subasta") /
                                            max(1, sum(1 for r in rs if r["route"] in MEASURED_ROUTES)))})
    cov = coverage(metas, expected)
    for c in cov:
        c["anomalies"] = sum(1 for r in recs if r["chain"] == c["chain"] and r.get("realized_anomaly"))
        c["paid_over_bonus"] = sum(1 for r in recs if r["chain"] == c["chain"] and r.get("paid_over_bonus"))
    chain_days = {c["chain"]: c["days"] for c in cov}
    anomalies = sorted((r for r in recs if r.get("realized_anomaly")), key=lambda r: -(r.get("bonus_usd") or 0))
    return {
        "entrypoints": entrypoints,
        "overall": overall,
        "by_chain_protocol": chain_rows,
        "routes": routes,
        "markets": market_rows,
        "sizes": sizes,
        "states": dict(states),
        "winners_top": [{"liquidator": w, "bonus_usd": v, "share": s} for w, v, s in winners_table(recs)[:15]],
        "payees": payees(recs),
        "bots_direct": bots(recs, "directa"),
        "bots_auction": bots(recs, "subasta"),
        "small_actor": small_actor(recs, chain_days),
        "coverage": cov,
        "anomalies": [{k: r.get(k) for k in ("chain", "tx_hash", "market_label", "bonus_usd", "realized_usd",
                                              "net_flows", "liquidator")} for r in anomalies[:20]],
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


def _share(part, whole):
    return part / whole if whole and abs(whole) >= 1 else None


def render_md(res, title_date):
    o = res["overall"]
    cov = res["coverage"]
    chains = ", ".join(c["chain"] for c in cov) or "—"
    days = sorted({round(c["days"], 1) for c in cov if c["days"]})
    dtxt = (f"{days[0]:g} días" if len(days) == 1 else "/".join(f"{d:g}" for d in days) + " días") if days else "?"
    eth_rows = [c for c in res["by_chain_protocol"] if c["chain"] == "ethereum"]
    f = o.get("flow") or {}
    L = []
    L.append(f"# Census del dinero · {title_date}")
    L.append("")
    L.append(f"Ventana: **{dtxt}** · cadenas: {chains} · protocolos: Aave V3 y Morpho Blue.")
    incomplete = [c for c in cov if (c["tramos_esperados"] and c["tramos"] < c["tramos_esperados"])
                  or not c["events_complete"] or c["budget_hit"] or c["interrupted"]]
    if incomplete:
        L.append("")
        L.append("> **Cobertura incompleta:** " + "; ".join(
            f"{c['chain']} ({c['tramos']}/{c['tramos_esperados'] or '?'} tramos"
            + (", eventos cortados" if not c["events_complete"] else "")
            + (f", {c['budget_hit']} tramos sin tiempo" if c["budget_hit"] else "")
            + (f", {c['interrupted']} interrumpidos" if c["interrupted"] else "") + ")"
            for c in incomplete) + ". Ver la sección de cobertura.")
    L.append("")
    L.append("## Respuesta corta")
    L.append("")
    L.append(f"1. **¿Cuánto dinero hay?** Bono total pagado a liquidadores: **{usd(o.get('bonus_usd'))}** "
             f"en {num(o.get('liquidations'))} liquidaciones.")
    L.append(f"2. **¿Quién se lo lleva?** {num(o.get('winners'))} liquidadores distintos; los 3 mayores se "
             f"llevan **{pct(o.get('top3_share'))}** del bono.")
    L.append(f"3. **¿Llegan a tiempo? ¿En cuántos bloques?** Mediana de **{num(o.get('blocks_median'))} bloques** "
             f"({num(o.get('seconds_median'))} s) desde la última actualización del oráculo; "
             f"**{pct(o.get('same_block_pct'))}** en el mismo bloque.")
    l2 = defaultdict(lambda: [0.0, 0.0])
    for c in res["by_chain_protocol"]:
        if c["chain"] != "ethereum":
            l2[c["chain"]][0] += c["builder_usd"]
            l2[c["chain"]][1] += c["bonus_usd"]
    l2_txt = ", ".join(f"{k} {pct(_share(v[0], v[1]))}" for k, v in sorted(l2.items()))
    if eth_rows:
        eb = sum(c["bonus_usd"] for c in eth_rows)
        L.append(f"4. **¿Qué porcentaje dejó al builder?** Ethereum: **{pct(_share(sum(c['builder_usd'] for c in eth_rows), eb))}** "
                 f"del bono (propina + pago directo al coinbase, que incluye las pujas de Chainlink SVR)."
                 + (f" En L2 no hay builder; la propina de prioridad fue: {l2_txt}." if l2_txt else ""))
    elif l2_txt:
        L.append(f"4. **¿Qué porcentaje dejó al builder?** En L2 no hay builder; la propina de prioridad fue: {l2_txt}.")
    oth = f.get("other") or {}
    L.append(f"5. **¿Cuánto se queda realmente el ganador?** En las {num(f.get('n'))} liquidaciones rastreables "
             f"({pct(_share(f.get('n'), f.get('n_total')))} del total): bono {usd(f.get('bonus'))}, "
             f"el ganador se quedó **{usd(f.get('kept'))} ({pct(_share(f.get('kept'), f.get('bonus')))})** "
             f"(de eso {usd(f.get('treasury'))} lo mandó a su tesorería); "
             f"a subastas de oráculo/OEV {usd(f.get('oev'))} ({pct(_share(f.get('oev'), f.get('bonus')))}), "
             f"al builder en directo {usd(f.get('builder_direct'))}, en propina {usd(f.get('priority'))}, "
             f"gas base {usd(f.get('gas_base'))}, resto (deslizamiento, comisiones) {usd(f.get('rest'))}. "
             f"Fuera de la cuenta: sin medir {num(oth.get('sin_medir', (0, 0))[0])} liq. ({usd(oth.get('sin_medir', (0, 0))[1])}), "
             f"sin rastro {num(oth.get('sin_rastro', (0, 0))[0])} ({usd(oth.get('sin_rastro', (0, 0))[1])}), "
             f"refinanciaciones {num(oth.get('refinanciacion', (0, 0))[0])} ({usd(oth.get('refinanciacion', (0, 0))[1])}).")
    L.append("")
    L.append("## ¿A dónde se va el bono?")
    L.append("")
    L.append("Solo liquidaciones rastreables (todos los movimientos de tokens y ETH valuados). Cada contraparte que solo "
             "recibe se clasifica: builder del bloque, subasta compartida (OEV: la usan 2 o más liquidadores o es una "
             "subasta conocida) o tesorería del mismo bot (cuenta como del ganador). Lo que va a contrapartes que "
             "devuelven algo (swaps, préstamos) queda en Resto: deslizamiento y comisiones. \"Sin rastro\": ni el "
             "ganador ni un sumidero se quedaron con el bono. \"Refinanciación\": el colateral volvió al protocolo en la "
             "misma tx (no es dinero que se mueva).")
    L.append("")
    L.append("| Cadena | Protocolo | Rastreables | Bono | Ganador | % | (tesorería) | OEV | Builder directo | Propina | Gas base | Resto | Sin medir · sin rastro · refin. |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for c in res["by_chain_protocol"]:
        fl = c["flow"]
        o = fl.get("other") or {}
        L.append(f"| {c['chain']} | {c['protocol']} | {fl['n']}/{fl['n_total']} | {usd(fl['bonus'])} | {usd(fl['kept'])} | "
                 f"{pct(_share(fl['kept'], fl['bonus']))} | {usd(fl.get('treasury'))} | {usd(fl['oev'])} | "
                 f"{usd(fl['builder_direct'])} | {usd(fl['priority'])} | {usd(fl['gas_base'])} | {usd(fl['rest'])} | "
                 + " · ".join(f"{o.get(k, (0, 0))[0]} ({usd(o.get(k, (0, 0))[1])})"
                              for k in ("sin_medir", "sin_rastro", "refinanciacion")) + " |")
    L.append("")
    L.append("## Por cadena y protocolo")
    L.append("")
    L.append("| Cadena | Protocolo | Liq. | Bono | Ganadores | Top 3 | Bloques (p25·med·p75) | Seg. | Mismo bloque | Builder (Eth) |")
    L.append("|---|---|---:|---:|---:|---:|---|---:|---:|---:|")
    for c in res["by_chain_protocol"]:
        bshare = pct(_share(c["builder_usd"], c["bonus_usd"])) if c["chain"] == "ethereum" else "n/a"
        L.append(f"| {c['chain']} | {c['protocol']} | {num(c['liquidations'])} | {usd(c['bonus_usd'])} | "
                 f"{num(c['winners'])} | {pct(c.get('top3_share'))} | "
                 f"{num(c.get('blocks_p25'))} · {num(c['blocks_median'])} · {num(c.get('blocks_p75'))} | "
                 f"{num(c['seconds_median'])} | {pct(c['same_block_pct'])} | {bshare} |")
    L.append("")
    L.append("## Subasta vs. directa")
    L.append("")
    L.append(f"\"Subasta\": lo pagado a terceros en ETH más la propina es ≥ {pct(ORDER_PAID_SHARE)} del bono (subasta de "
             f"oráculo, builder o guerra de prioridad). \"Directa\": el ganador no pagó por el orden. "
             f"\"Sin medir\": faltaron trazas o precios.")
    L.append("")
    L.append("| Cadena | Ruta | Liq. | Bono | Ganador se queda | % | Mediana por liq. | Ganadores | Bloques |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for s in res["routes"]:
        L.append(f"| {s['chain']} | {s['route']} | {s['liquidations']} | {usd(s['bonus_usd'])} | "
                 f"{usd(s['realized_usd']) if s['route'] in MEASURED_ROUTES else '—'} | {pct(s['kept_share'])} | "
                 f"{usd(s['realized_median'])} | {s['winners']} | {num(s['blocks_median'])} |")
    L.append("")
    L.append("## ¿Queda margen para un actor pequeño?")
    L.append("")
    L.append("Liquidaciones directas (sin pagar subasta ni builder) y lo que realmente se quedó el ganador.")
    L.append("")
    L.append("| Cadena | Días | Directas / medidas / total | Se quedaron | ≥ $10 (n · $ · top) | ≥ $100 (n · $ · top) | Ganadores | Bloques | ≥ 2 bloques |")
    L.append("|---|---:|---|---:|---|---|---:|---:|---:|")
    for s in res["small_actor"]:
        L.append(f"| {s['chain']} | {num(s['days'], 1)} | {s['direct']} / {s['measured']} / {s['total']} | {usd(s['kept_usd'])} | "
                 f"{s['ge10']} · {usd(s['ge10_usd'])} · {pct(s['ge10_top_share'])} | "
                 f"{s['ge100']} · {usd(s['ge100_usd'])} · {pct(s['ge100_top_share'])} | {s['winners']} | "
                 f"{num(s['blocks_median'])} | {pct(s['late_pct'])} |")
    L.append("")
    L.append("\"top\": parte del neto que se llevó el mayor ganador de ese grupo. \"≥ 2 bloques\": liquidaciones que "
             "llegaron 2 o más bloques después del oráculo (no fue carrera de mismo bloque).")
    L.append("")
    L.append("### Bots que ganan por fuera de subastas")
    L.append("")
    L.append("| Cadena | Contrato liquidador | Firmantes | Liq. | Bono | Se quedó | % | Mediana | Bloques | Días | Mercados |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for b in res["bots_direct"][:20]:
        L.append(f"| {b['chain']} | `{b['liquidator']}` | {b['signers']} | {b['liquidations']} | {usd(b['bonus_usd'])} | "
                 f"{usd(b['realized_usd'])} | {pct(b['kept_share'])} | {usd(b['realized_median'])} | "
                 f"{num(b['blocks_median'])} | {b['days_active']} | {b['markets']} |")
    L.append("")
    L.append("### Contratos que pagan por el orden (subastas)")
    L.append("")
    L.append("| Cadena | Contrato liquidador | Firmantes | Liq. | Bono | Se quedó | % | Pagado por orden | Bloques |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for b in res["bots_auction"][:12]:
        L.append(f"| {b['chain']} | `{short(b['liquidator'])}` | {b['signers']} | {b['liquidations']} | {usd(b['bonus_usd'])} | "
                 f"{usd(b['realized_usd'])} | {pct(b['kept_share'])} | {usd(b['order_paid_usd'])} | {num(b['blocks_median'])} |")
    L.append("")
    L.append("### ¿A quién va el ETH que sale del liquidador?")
    L.append("")
    L.append("\"compartido\": cobra de 2 o más liquidadores (subasta, builder). \"un_solo_liquidador\": puede ser la "
             "tesorería del mismo bot; si lo es, ese pago es ganancia y no OEV.")
    L.append("")
    L.append("| Cadena | Destinatario | Tipo | USD | Liq. | Liquidadores | Es la entrada |")
    L.append("|---|---|---|---:|---:|---:|---|")
    for p_ in res.get("payees", []):
        L.append(f"| {p_['chain']} | `{p_['payee']}` | {p_['kind']} | {usd(p_['usd'])} | {p_['liquidations']} | "
                 f"{p_['liquidators']} | {'sí' if p_['is_entry'] else 'no'} |")
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
    L.append("| Cadena | Mercado | Liq. | Bono | Real | % quedó | Directas | Ganadores | Top | Bloques | Estado |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for m in res["markets"][:15]:
        L.append(f"| {m['chain']} | {m['market_label']} | {m['liquidations']} | {usd(m['bonus_usd'])} | "
                 f"{usd(m['realized_usd'])} | {pct(m['kept_share'])} | {m['direct_liquidations']} | {m['winners']} | "
                 f"{pct(m['top_winner_share'])} | {num(m['blocks_median'])} | {m['state']} |")
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
    L.append("| Bono | Liq. | Real total | Real mediano | % quedó | Directas | Ganadores |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    for s in res["sizes"]:
        rng = f"{usd(s['lo'])}–{usd(s['hi'])}" if s["hi"] != float("inf") else f"≥ {usd(s['lo'])}"
        L.append(f"| {rng} | {num(s.get('liquidations'))} | {usd(s.get('realized_usd'))} | "
                 f"{usd(s.get('realized_median'))} | {pct(s.get('kept_share'))} | {num(s.get('direct_liquidations'))} | "
                 f"{num(s.get('winners'))} |")
    L.append("")
    L.append("## ¿Por dónde entran? (contrato llamado por la transacción)")
    L.append("")
    L.append("Si un mismo contrato recibe transacciones de muchos firmantes distintos y casi todo sale en ETH, "
             "es una subasta o un enrutador compartido, no el bot de alguien.")
    L.append("")
    L.append("| Cadena | Contrato | Liq. | Firmantes | Bono | % quedó | A terceros | % subasta |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|")
    for e in res.get("entrypoints", []):
        L.append(f"| {e['chain']} | `{short(e['tx_to'])}` | {e['liquidations']} | {e['senders']} | {usd(e['bonus_usd'])} | "
                 f"{pct(e['kept_share'])} | {usd(e['third_party_usd'])} | {pct(e['auction_pct'])} |")
    L.append("")
    L.append("## Ganadores principales (por bono)")
    L.append("")
    for w in res["winners_top"][:10]:
        L.append(f"- `{w['liquidator']}` — {usd(w['bonus_usd'])} ({pct(w['share'])})")
    L.append("")
    L.append("## Cobertura de la medición")
    L.append("")
    L.append("| Cadena | Tramos | Días | Eventos | Valuados | Real completo | Con bloques de oráculo | Trazas de ETH | Precio | Sin tiempo |")
    L.append("|---|---|---:|---:|---:|---:|---:|---|---|---:|")
    for c in cov:
        ps = c["prices"]
        L.append(f"| {c['chain']} | {c['tramos']}/{c['tramos_esperados'] or c['tramos']} | {num(c['days'], 1)} | {c['events']} | "
                 f"{c['with_bonus_usd']} | {c['with_realized_complete']} ({pct(_share(c['with_realized_complete'], c['events']))}) | "
                 f"{c['with_oracle_delta']} ({pct(_share(c['with_oracle_delta'], c['events']))}) | "
                 f"{', '.join(f'{k}: {v}' for k, v in c['native'].items()) or '—'} | "
                 f"oráculo {ps.get('oraculo', 0)}, mercado {ps.get('defillama', 0)}, sin {ps.get('sin_precio', 0)} | "
                 f"{c['budget_hit']} |")
    over = [(c["chain"], c["paid_over_bonus"]) for c in cov if c.get("paid_over_bonus")]
    if over:
        L.append("")
        L.append("Liquidaciones cuya tx pagó por el orden más de 1.5× su bono (probable liquidación de otro protocolo "
                 "o arbitraje en la misma tx; el pago completo cuenta como OEV/builder): "
                 + ", ".join(f"{c}: {n}" for c, n in over) + ".")
    if res.get("anomalies"):
        L.append("")
        L.append(f"Netos fuera de rango (no se cuentan como medidos; revisar a mano): "
                 + "; ".join(f"{a['chain']} `{a['tx_hash']}` bono {usd(a['bonus_usd'])}, neto {usd(a['realized_usd'])} "
                             f"({a['net_flows'] or '—'})" for a in res["anomalies"][:8]) + ".")
    errs = [(c["chain"], k, v) for c in cov for k, v in c["trace_errors"].items()]
    if errs:
        L.append("")
        L.append("Errores de trazas más comunes: " + "; ".join(f"{c}: {k} ({v})" for c, k, v in errs[:8]) + ".")
    L.append("")
    L.append("## Qué NO dice este census")
    L.append("")
    L.append("- \"Se queda\" es lo que se quedaron los ganadores actuales, no lo que ganaría NQC: para eso hay que "
             "ganarles la carrera o la subasta.")
    L.append("- Para medir lo que se quedan se cuenta como del liquidador: el firmante, el contrato que llamó al protocolo y "
             "las cuentas sin código que solo reciben. Si un bot manda su ganancia a otro contrato propio, aquí se "
             "ve como pago a terceros y sale menor (y la liquidación puede clasificarse como \"subasta\").")
    L.append("- El bono está a precio de oráculo (o de mercado si no hubo nodo de archivo); lo que se quedan ya incluye "
             "el deslizamiento de vender el colateral.")
    L.append("- En L2 no hay subasta de builders; la propina de prioridad sí se cuenta. Las pujas de Timeboost "
             "(Arbitrum) se pagan por fuera de la transacción y no se ven aquí.")
    L.append("- No incluye pre-liquidaciones de Morpho ni otros protocolos (Spark, Compound, Euler, Fluid).")
    L.append("- No reconcilia todas las posiciones del alcance (puerta \"cobertura del mercado\" de Omega): solo mide "
             "las liquidaciones que sí ocurrieron.")
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
    with open(os.path.join(out_dir, "bots_directos.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=BOT_FIELDS, extrasaction="ignore")
        w.writeheader()
        for b in res["bots_direct"]:
            w.writerow(b)
    with open(os.path.join(out_dir, "resumen.json"), "w") as fh:
        json.dump({k: v for k, v in res.items() if k not in ("markets", "metas")}
                  | {"markets_top50": res["markets"][:50]}, fh, indent=2, default=str)
    md = render_md(res, title_date)
    with open(os.path.join(out_dir, "RESUMEN.md"), "w") as fh:
        fh.write(md)
    return md
