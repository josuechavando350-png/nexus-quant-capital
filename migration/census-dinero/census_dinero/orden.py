"""Orden de las transacciones dentro de un bloque de Base: ¿se ordenan por prioridad dentro de cada trozo de 200 ms?

Todo el análisis de "quién reaccionó y quién iba empaquetado" supone que, dentro de un trozo (Flashblock), el secuenciador pone
primero a quien paga más propina por unidad de gas. Este módulo lo comprueba con bloques reales: guarda la secuencia de propinas
de un bloque y mide cuántos pares consecutivos suben o bajan, dentro de cada trozo y en la frontera entre dos trozos.

Solo lee lo que ya devolvió el RPC (`eth_getBlockByNumber` con las transacciones completas); no toca la red.
"""

from .shadow_live import quantiles


def block_tips(block):
    """(tarifa base, propina por unidad de gas en wei de cada transacción, en el orden del bloque). `None` para los depósitos de la L1."""
    base = int(block.get("baseFeePerGas") or "0x0", 16)
    tips = []
    for tx in block.get("transactions") or []:
        if not isinstance(tx, dict) or int(tx.get("type") or "0x0", 16) == 0x7E:
            tips.append(None)
        elif tx.get("maxPriorityFeePerGas") is not None and tx.get("maxFeePerGas") is not None:
            tips.append(max(0, min(int(tx["maxPriorityFeePerGas"], 16), int(tx["maxFeePerGas"], 16) - base)))
        else:
            tips.append(max(0, int(tx.get("gasPrice") or "0x0", 16) - base))
    return base, tips


def ascents(tips):
    """Cuántas veces la propina sube de una transacción a la siguiente (ignora los depósitos)."""
    xs = [t for t in tips if t is not None]
    return sum(1 for a, b in zip(xs, xs[1:]) if b > a)


def compare(a, b):
    return None if a is None or b is None else ("baja" if b < a else "igual" if b == a else "sube")


def analyze_order(samples, profiles=None):
    """Resumen del orden de propinas. `samples`: [{"bloque", "tips"}]. `profiles`: perfiles de trozos del vivo
    ([{"bloque", "trozos": [[ms, transacciones acumuladas]]}]); con ellos se separan los pares de dentro de un trozo de los de la frontera."""
    profiles = {p["bloque"]: p for p in (profiles or []) if p.get("trozos")}
    out = {"bloques": len(samples), "transacciones": quantiles([len(s["tips"]) for s in samples]),
           "ascensos_por_bloque": quantiles([ascents(s["tips"]) for s in samples]),
           "con_perfil": 0, "dentro": {"baja": 0, "igual": 0, "sube": 0}, "frontera": {"baja": 0, "igual": 0, "sube": 0}}
    for s in samples:
        p = profiles.get(s["bloque"])
        tips = s["tips"]
        if not p:
            continue
        cuts = {n for _, n in p["trozos"] if 0 < n < len(tips)}          # índice de la primera transacción de cada trozo nuevo
        if not cuts:
            continue
        out["con_perfil"] += 1
        for i in range(len(tips) - 1):
            rel = compare(tips[i], tips[i + 1])
            if rel:
                out["frontera" if i + 1 in cuts else "dentro"][rel] += 1
    return out
