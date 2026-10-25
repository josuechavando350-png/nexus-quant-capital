"""Orden de las transacciones dentro de un bloque de Base: ¿se ordenan por prioridad dentro de cada trozo de 200 ms?

Todo el análisis de "quién reaccionó y quién iba empaquetado" supone que, dentro de un trozo (Flashblock), el secuenciador pone
primero a quien paga más propina por unidad de gas. Este módulo lo comprueba con bloques reales: guarda la secuencia de propinas
de un bloque y mide cuántos pares consecutivos suben o bajan, dentro de cada trozo y en la frontera entre dos trozos.

Solo lee lo que ya devolvió el RPC (`eth_getBlockByNumber` con las transacciones completas); no toca la red.
"""

from collections import Counter

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


def expected_random_ascents(tips):
    """Cuántas subidas de propina habría, en promedio, si las mismas transacciones estuvieran en orden de llegada al azar
    (probabilidad de que dos vecinas tengan propinas distintas, entre dos: la mitad suben)."""
    xs = [t for t in tips if t is not None]
    n = len(xs)
    if n < 2:
        return 0.0
    same = sum(c * (c - 1) for c in Counter(xs).values())
    return (n - 1) * (1 - same / (n * (n - 1))) / 2


# --- Qué pasó con una liquidación respecto a la actualización del oráculo --------------------------
MAX_ENTRE = 700              # hasta cuántas propinas entre la actualización y la liquidación se guardan completas
EMPAQUETADA_GAP = 50         # misma propina que la actualización y a esta distancia o menos: iban juntas (más lejos puede ser casualidad)
LLENO_GAP = 0.25             # una separación de esta parte del bloque o más no cabe en un solo trozo

CLASES = {
    "empaquetada": "misma propina que la actualización y pegada a ella: iba empaquetada (subasta OEV)",
    "mismo_trozo": "pico de propina justo después de la actualización, en su mismo trozo: alguien vio la actualización antes de que se confirmara",
    "trozo_siguiente": "en un trozo posterior: reaccionó después de que se publicó el trozo de la actualización",
    "ambigua": "paga menos que la actualización y sin pico: pudo ser el mismo trozo o uno posterior",
}


def propinas_alrededor(tips, u, l):
    """Lo que hace falta de un bloque para clasificar una liquidación: la propina de la actualización (índice u) y de la liquidación
    (índice l), las de sus vecinas y todas las de en medio si no son demasiadas. `None` si no se puede."""
    if not tips or u is None or l is None or not 0 <= u < l < len(tips):
        return None
    return {"u": tips[u], "l": tips[l], "gap": l - u, "n": len(tips),
            "antes_de_l": tips[l - 1] if l > 0 else None, "despues_de_l": tips[l + 1] if l + 1 < len(tips) else None,
            "entre": tips[u:l + 1] if l - u <= MAX_ENTRE else None}


def clasificar(p):
    """Clase de una liquidación según `propinas_alrededor`. Se apoya en que dentro de un trozo las propinas bajan: una que sube justo en la
    liquidación y vuelve al nivel de antes es un pico que entró tarde en el mismo trozo; una que está dentro de la cabeza ordenada de otro
    trozo, o que paga más que la actualización sin ser un pico, está en un trozo posterior."""
    if not p or p.get("u") is None or p.get("l") is None:
        return None
    u, l, gap, n = p["u"], p["l"], p["gap"], p.get("n")
    if l == u and gap <= EMPAQUETADA_GAP:
        return "empaquetada"
    if n and gap >= LLENO_GAP * n:
        return "trozo_siguiente"
    prev, nxt = p.get("antes_de_l"), p.get("despues_de_l")
    if prev is not None and l > prev:
        return "trozo_siguiente" if nxt is not None and nxt > prev else "mismo_trozo"
    return "trozo_siguiente" if l > u else "ambigua"


def validate_classifier(samples, profiles, n_tx=None):
    """Prueba la regla de `clasificar` con bloques en vivo cuyos trozos se conocen (perfil de `flash_bloques.jsonl`): cada subida de
    propina es el comienzo de un trozo o un pico dentro de uno, y las transacciones de la cabeza de un trozo nuevo están en un trozo
    posterior al de la última del trozo anterior. Solo bloques vistos enteros (11 fotos y el mismo tamaño que el bloque sellado)."""
    profiles = {p["bloque"]: p for p in (profiles or []) if p.get("trozos")}
    out = {"bloques": 0, "fronteras": {"n": 0, "bien": 0}, "picos": {"n": 0, "bien": 0}, "cabezas": {"n": 0, "bien": 0}}
    for smp in samples:
        p, tips = profiles.get(smp["bloque"]), smp["tips"]
        if not p or len(p["trozos"]) != 11 or (n_tx and n_tx.get(smp["bloque"]) not in (None, len(tips))):
            continue
        n = len(tips)
        cuts = sorted({c for _, c in p["trozos"] if 0 < c < n})
        cutset = set(cuts)
        out["bloques"] += 1
        for i in range(2, n - 1):
            a, b = tips[i - 1], tips[i]
            if a is None or b is None or b <= a:
                continue
            got = clasificar({"u": a, "l": b, "gap": 1, "n": n, "antes_de_l": a, "despues_de_l": tips[i + 1]})
            key, want = ("fronteras", "trozo_siguiente") if i in cutset else ("picos", "mismo_trozo")
            out[key]["n"] += 1
            out[key]["bien"] += got == want
        for c in cuts:
            for k in (1, 2, 3):
                L = c + k
                if L + 1 >= n or tips[c - 1] is None or tips[L] is None or any(x in cutset for x in range(c + 1, L + 1)):
                    continue
                got = clasificar({"u": tips[c - 1], "l": tips[L], "gap": L - c + 1, "n": n, "antes_de_l": tips[L - 1], "despues_de_l": tips[L + 1]})
                out["cabezas"]["n"] += 1
                out["cabezas"]["bien"] += got == "trozo_siguiente"
    return out


def compare(a, b):
    return None if a is None or b is None else ("baja" if b < a else "igual" if b == a else "sube")


def analyze_order(samples, profiles=None):
    """Resumen del orden de propinas. `samples`: [{"bloque", "tips"}]. `profiles`: perfiles de trozos del vivo
    ([{"bloque", "trozos": [[ms, transacciones acumuladas]]}]); con ellos se separan los pares de dentro de un trozo de los de la frontera."""
    profiles = {p["bloque"]: p for p in (profiles or []) if p.get("trozos")}
    out = {"bloques": len(samples), "transacciones": quantiles([len(s["tips"]) for s in samples]),
           "ascensos_por_bloque": quantiles([ascents(s["tips"]) for s in samples]),
           "ascensos_si_fuera_al_azar": quantiles([round(expected_random_ascents(s["tips"])) for s in samples]),
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
