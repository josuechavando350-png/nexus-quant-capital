"""Morpho Blue exacto: aritmética entera, ABI mínimo, eventos y multicall. Solo lectura.

Las fórmulas son un puerto 1:1 de morpho-org/morpho-blue (Morpho.sol, SharesMathLib.sol,
MathLib.sol, ConstantsLib.sol), contrastado contra su código el 25 oct 2026. Todo es entero:
el redondeo (arriba o abajo) decide si una posición es liquidable por una unidad.
"""

from dataclasses import dataclass, replace

from .abi import address_from_topic, address_from_word, encode_address, encode_bytes32, strip0x
from .keccak import selector, topic

WAD = 10 ** 18
ORACLE_PRICE_SCALE = 10 ** 36
VIRTUAL_SHARES = 10 ** 6
VIRTUAL_ASSETS = 1
MAX_LIQUIDATION_INCENTIVE_FACTOR = 115 * 10 ** 16      # 1.15
LIQUIDATION_CURSOR = 30 * 10 ** 16                     # 0.3
MULTICALL3 = "0xca11bde05977b3631167028862be2a173976ca11"
ZERO = "0x" + "0" * 40


@dataclass(frozen=True)
class Params:
    loan: str
    collateral: str
    oracle: str
    irm: str
    lltv: int


@dataclass(frozen=True)
class MarketState:
    total_supply_assets: int
    total_supply_shares: int
    total_borrow_assets: int
    total_borrow_shares: int
    last_update: int
    fee: int


# -- aritmética (MathLib / SharesMathLib) ---------------------------------------------
def mul_div_down(x, y, d):
    return x * y // d


def mul_div_up(x, y, d):
    return (x * y + (d - 1)) // d


def w_mul_down(x, y):
    return mul_div_down(x, y, WAD)


def w_div_down(x, y):
    return mul_div_down(x, WAD, y)


def w_div_up(x, y):
    return mul_div_up(x, WAD, y)


def to_shares_down(assets, total_assets, total_shares):
    return mul_div_down(assets, total_shares + VIRTUAL_SHARES, total_assets + VIRTUAL_ASSETS)


def to_assets_down(shares, total_assets, total_shares):
    return mul_div_down(shares, total_assets + VIRTUAL_ASSETS, total_shares + VIRTUAL_SHARES)


def to_shares_up(assets, total_assets, total_shares):
    return mul_div_up(assets, total_shares + VIRTUAL_SHARES, total_assets + VIRTUAL_ASSETS)


def to_assets_up(shares, total_assets, total_shares):
    return mul_div_up(shares, total_assets + VIRTUAL_ASSETS, total_shares + VIRTUAL_SHARES)


def w_taylor_compounded(x, n):
    first = x * n
    second = mul_div_down(first, first, 2 * WAD)
    third = mul_div_down(second, first, 3 * WAD)
    return first + second + third


def lif(lltv):
    """Factor de incentivo de liquidación: min(1.15, 1 / (1 - 0.3 * (1 - lltv))), en WAD."""
    return min(MAX_LIQUIDATION_INCENTIVE_FACTOR, w_div_down(WAD, WAD - w_mul_down(LIQUIDATION_CURSOR, WAD - lltv)))


# -- salud y liquidación ---------------------------------------------------------------
def borrowed_assets(borrow_shares, m):
    return to_assets_up(borrow_shares, m.total_borrow_assets, m.total_borrow_shares)


def max_borrow(collateral, price, lltv):
    return w_mul_down(mul_div_down(collateral, price, ORACLE_PRICE_SCALE), lltv)


def is_healthy(borrow_shares, collateral, price, lltv, m):
    if borrow_shares == 0:
        return True
    return max_borrow(collateral, price, lltv) >= borrowed_assets(borrow_shares, m)


def health_ratio(borrow_shares, collateral, price, lltv, m):
    """max_borrow / borrowed (float, solo para ordenar y mostrar); <1 es liquidable. None sin deuda."""
    borrowed = borrowed_assets(borrow_shares, m)
    if borrowed == 0:
        return None
    return max_borrow(collateral, price, lltv) / borrowed


def liquidation_price(borrow_shares, collateral, lltv, m):
    """Precio del oráculo (escala 1e36) bajo el cual la posición es liquidable. None sin deuda o sin colateral."""
    borrowed = borrowed_assets(borrow_shares, m)
    if borrowed == 0 or collateral == 0 or lltv == 0:
        return None
    return mul_div_up(mul_div_up(borrowed, WAD, lltv), ORACLE_PRICE_SCALE, collateral)


def full_quote(borrow_shares, collateral, price, lltv, m):
    """La liquidación más grande posible de una posición insana.

    Repaga toda la deuda si el colateral alcanza para el incentivo; si no, embarga todo el
    colateral, repaga lo que ese colateral cubre y el resto queda como deuda mala."""
    f = lif(lltv)
    tba, tbs = m.total_borrow_assets, m.total_borrow_shares
    repaid_shares = borrow_shares
    seized = mul_div_down(w_mul_down(to_assets_down(repaid_shares, tba, tbs), f), ORACLE_PRICE_SCALE, price)
    if seized > collateral:
        seized = collateral
        quoted = mul_div_up(seized, price, ORACLE_PRICE_SCALE)
        repaid_shares = min(borrow_shares, to_shares_up(w_div_up(quoted, f), tba, tbs))
    repaid_assets = to_assets_up(repaid_shares, tba, tbs)
    seized_quoted = mul_div_down(seized, price, ORACLE_PRICE_SCALE)
    new_tba = max(0, tba - repaid_assets)
    new_tbs = tbs - repaid_shares
    bad_shares = bad_assets = 0
    if collateral - seized == 0:
        bad_shares = borrow_shares - repaid_shares
        bad_assets = min(new_tba, to_assets_up(bad_shares, new_tba, new_tbs))
    return {
        "lif": f, "repaid_shares": repaid_shares, "repaid_assets": repaid_assets, "seized_assets": seized,
        "seized_quoted": seized_quoted, "bonus_assets": seized_quoted - repaid_assets,
        "bad_debt_shares": bad_shares, "bad_debt_assets": bad_assets,
    }


def predict_from_repaid_shares(repaid_shares, price, lltv, m):
    """(embargado, repagado) que da el contrato cuando el liquidador fija `repaidShares`."""
    f = lif(lltv)
    tba, tbs = m.total_borrow_assets, m.total_borrow_shares
    seized = mul_div_down(w_mul_down(to_assets_down(repaid_shares, tba, tbs), f), ORACLE_PRICE_SCALE, price)
    return seized, to_assets_up(repaid_shares, tba, tbs)


def predict_from_seized_assets(seized, price, lltv, m):
    """(repaidShares, repagado) que da el contrato cuando el liquidador fija `seizedAssets`."""
    f = lif(lltv)
    tba, tbs = m.total_borrow_assets, m.total_borrow_shares
    quoted = mul_div_up(seized, price, ORACLE_PRICE_SCALE)
    shares = to_shares_up(w_div_up(quoted, f), tba, tbs)
    return shares, to_assets_up(shares, tba, tbs)


def accrue(m, rate_per_second, now_ts):
    """Estado del mercado después de `_accrueInterest` en `now_ts` (solo los totales de deuda y oferta)."""
    elapsed = now_ts - m.last_update
    if elapsed <= 0 or rate_per_second <= 0 or m.total_borrow_assets == 0:
        return m
    interest = w_mul_down(m.total_borrow_assets, w_taylor_compounded(rate_per_second, elapsed))
    return replace(m, total_borrow_assets=m.total_borrow_assets + interest,
                   total_supply_assets=m.total_supply_assets + interest, last_update=now_ts)


# -- ABI --------------------------------------------------------------------------------
SEL_MARKET = selector("market(bytes32)")
SEL_POSITION = selector("position(bytes32,address)")
SEL_PARAMS = selector("idToMarketParams(bytes32)")
SEL_PRICE = selector("price()")
SEL_RATE = selector("borrowRateView((address,address,address,address,uint256),"
                    "(uint128,uint128,uint128,uint128,uint128,uint128))")
SEL_AGGREGATE3 = selector("aggregate3((address,bool,bytes)[])")
SEL_BLOCK_NUMBER = selector("getBlockNumber()")
SEL_DECIMALS = selector("decimals()")
SEL_SYMBOL = selector("symbol()")


def _w(n):
    return n.to_bytes(32, "big")


def _int(b, i):
    if i < 0 or i + 32 > len(b):
        raise ValueError("datos ABI truncados")
    return int.from_bytes(b[i:i + 32], "big")


def call_market(market_id):
    return SEL_MARKET + encode_bytes32(market_id)


def call_position(market_id, user):
    return SEL_POSITION + encode_bytes32(market_id) + encode_address(user)


def call_params(market_id):
    return SEL_PARAMS + encode_bytes32(market_id)


def call_rate(params, m):
    words = [int(strip0x(params.loan), 16), int(strip0x(params.collateral), 16), int(strip0x(params.oracle), 16),
             int(strip0x(params.irm), 16), params.lltv, m.total_supply_assets, m.total_supply_shares,
             m.total_borrow_assets, m.total_borrow_shares, m.last_update, m.fee]
    return SEL_RATE + "".join(_w(x).hex() for x in words)


def _as_bytes(data):
    return data if isinstance(data, (bytes, bytearray)) else bytes.fromhex(strip0x(data or "0x"))


def decode_market(data):
    b = _as_bytes(data)
    if len(b) != 6 * 32:
        raise ValueError(f"market() devolvió {len(b)} bytes, se esperaban 192")
    return MarketState(*(_int(b, 32 * i) for i in range(6)))


def decode_position(data):
    """(supply_shares, borrow_shares, collateral)."""
    b = _as_bytes(data)
    if len(b) != 3 * 32:
        raise ValueError(f"position() devolvió {len(b)} bytes, se esperaban 96")
    return _int(b, 0), _int(b, 32), _int(b, 64)


def decode_params(data):
    b = _as_bytes(data)
    if len(b) != 5 * 32:
        raise ValueError(f"idToMarketParams() devolvió {len(b)} bytes, se esperaban 160")
    return Params(address_from_word(_int(b, 0)), address_from_word(_int(b, 32)), address_from_word(_int(b, 64)),
                  address_from_word(_int(b, 96)), _int(b, 128))


def decode_uint(data):
    b = _as_bytes(data)
    if len(b) < 32:
        raise ValueError("respuesta vacía")
    return _int(b, 0)


# -- Multicall3 --------------------------------------------------------------------------
def encode_aggregate3(calls):
    """calls: [(destino, permitir_fallo, calldata_hex)] -> calldata de aggregate3 (hex con 0x)."""
    items = []
    for target, allow, data in calls:
        raw = bytes.fromhex(strip0x(data))
        items.append(_w(int(strip0x(target), 16)) + _w(1 if allow else 0) + _w(0x60) + _w(len(raw)) + raw
                     + b"\x00" * ((-len(raw)) % 32))
    offsets, cur = [], len(items) * 32
    for it in items:
        offsets.append(cur)
        cur += len(it)
    body = _w(len(items)) + b"".join(_w(o) for o in offsets) + b"".join(items)
    return SEL_AGGREGATE3 + (_w(0x20) + body).hex()


def decode_aggregate3(result):
    """-> [(éxito, bytes)] en el orden de las llamadas."""
    b = _as_bytes(result)
    arr = _int(b, 0)
    n = _int(b, arr)
    base = arr + 32
    out = []
    for i in range(n):
        t = base + _int(b, base + 32 * i)
        ok = _int(b, t) != 0
        boff = _int(b, t + 32)
        blen = _int(b, t + boff)
        start = t + boff + 32
        if start + blen > len(b):
            raise ValueError("resultado de multicall truncado")
        out.append((ok, bytes(b[start:start + blen])))
    return out


# -- eventos -----------------------------------------------------------------------------
EVENT_SIGNATURES = {
    "Borrow": "Borrow(bytes32,address,address,address,uint256,uint256)",
    "Repay": "Repay(bytes32,address,address,uint256,uint256)",
    "SupplyCollateral": "SupplyCollateral(bytes32,address,address,uint256)",
    "WithdrawCollateral": "WithdrawCollateral(bytes32,address,address,address,uint256)",
    "Liquidate": "Liquidate(bytes32,address,address,uint256,uint256,uint256,uint256,uint256)",
}
EVENT_TOPICS = {name: topic(sig) for name, sig in EVENT_SIGNATURES.items()}
KIND_BY_TOPIC = {t: name for name, t in EVENT_TOPICS.items()}
BOOK_EVENTS = list(EVENT_TOPICS.values())


def decode_event(lg):
    """Decodifica un log de Morpho Blue. Devuelve None si no es uno de los eventos de posiciones.

    El resultado trae `user` (la cuenta cuya posición cambia), `d_shares` (cambio en shares de
    deuda) y `d_collateral` (cambio en colateral)."""
    t = [x.lower() for x in lg.get("topics") or []]
    kind = KIND_BY_TOPIC.get(t[0]) if t else None
    if kind is None:
        return None
    data = strip0x(lg.get("data") or "0x")
    if len(data) % 64:
        raise ValueError("datos del log no son múltiplo de 32 bytes")
    w = [int(data[i:i + 64], 16) for i in range(0, len(data), 64)]
    ev = {"kind": kind, "market": t[1], "block": int(lg["blockNumber"], 16), "log_index": int(lg["logIndex"], 16),
          "tx_hash": lg["transactionHash"].lower(), "tx_index": int(lg.get("transactionIndex") or "0x0", 16)}
    shape = {"Borrow": (4, 3), "Repay": (4, 2), "SupplyCollateral": (4, 1), "WithdrawCollateral": (4, 2),
             "Liquidate": (4, 5)}[kind]
    if (len(t), len(w)) != shape:
        raise ValueError(f"{kind}: forma inesperada ({len(t)} topics, {len(w)} palabras)")
    if kind == "Borrow":
        ev.update(user=address_from_topic(t[2]), receiver=address_from_topic(t[3]), caller=address_from_word(w[0]),
                  assets=w[1], shares=w[2], d_shares=w[2], d_collateral=0)
    elif kind == "Repay":
        ev.update(caller=address_from_topic(t[2]), user=address_from_topic(t[3]), assets=w[0], shares=w[1],
                  d_shares=-w[1], d_collateral=0)
    elif kind == "SupplyCollateral":
        ev.update(caller=address_from_topic(t[2]), user=address_from_topic(t[3]), assets=w[0], d_shares=0,
                  d_collateral=w[0])
    elif kind == "WithdrawCollateral":
        ev.update(user=address_from_topic(t[2]), receiver=address_from_topic(t[3]), caller=address_from_word(w[0]),
                  assets=w[1], d_shares=0, d_collateral=-w[1])
    else:
        ev.update(caller=address_from_topic(t[2]), user=address_from_topic(t[3]), borrower=address_from_topic(t[3]),
                  repaid_assets=w[0], repaid_shares=w[1], seized_assets=w[2], bad_debt_assets=w[3],
                  bad_debt_shares=w[4], d_shares=-(w[1] + w[4]), d_collateral=-w[2])
    return ev


def norm_id(market_id):
    m = "0x" + strip0x(market_id).lower()
    if len(m) != 66:
        raise ValueError(f"id de mercado inválido: {market_id}")
    return m

