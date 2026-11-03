"""Entradas reproducibles para evaluar financiación; no calcula ni certifica P&L.

Se conserva la foto usada por el filtro, sin nuevas consultas en su ruta crítica.
Las lecturas originales son por número de bloque: el hash observado no sustituye
una nueva simulación anclada ni una comprobación de canonicalidad.
"""

from collections import Counter
from dataclasses import asdict

SCHEMA = "nqc-shadow-financing-input-v1"
PENDING = (
    "prestamista_liquidez_comision",
    "ruta_swap_salida_minima",
    "simulacion_atomica_y_repago",
    "titan_cobertura_cadena_y_candidata",
    "gas_l1_l2_y_reembolso_sin_doble_conteo",
    "compensacion_builder",
)


def policy():
    return {"gas_payer": "TITAN", "principal_source": "FLASH_LOAN",
            "operator_gas_allowance": 0, "operator_principal_allowance": 0,
            "operator_prefund": False, "own_gas_fallback": False}


def capture(chain_id, morpho, info, pos, state, price, quote, hdr, n, accrued):
    """Cantidades raw en cadenas decimales: evita pérdida de enteros en lectores JS."""
    return {
        "schema": SCHEMA, "politica": policy(),
        "ancla": {"chain_id": chain_id, "bloque": n, "hash_observado": hdr.get("hash"),
                  "timestamp": hdr["ts"], "lecturas_por": "numero_de_bloque",
                  "canonicalidad_revalidada": False},
        "morpho": morpho, "mercado": info.id,
        "parametros": {**asdict(info.params), "lltv": str(info.params.lltv)},
        "decimales": {"loan": info.loan_dec, "collateral": info.coll_dec},
        "estado_usado_raw": {k: str(v) for k, v in asdict(state).items()},
        "interes_acumulado_por_modelo": accrued,
        "posicion_raw": {"borrow_shares": str(pos.borrow_shares), "collateral": str(pos.collateral)},
        "precio_oraculo_raw": str(price),
        "cotizacion_modelo_raw": {k: str(v) for k, v in quote.items()},
        "prestamo_flash": {"activo": info.params.loan, "principal_modelo_raw": str(quote["repaid_assets"]),
                           "prestamista": None, "liquidez_raw": None, "comision_raw": None},
        "cobertura_titan": None, "simulacion_propia": None,
        "neto_propio_usd": None, "beneficio_realizado_usd": None,
        "pendientes": list(PENDING),
    }


def summarize(decisions):
    captures = [r["financiacion"] for r in decisions
                if isinstance(r.get("financiacion"), dict) and r["financiacion"].get("schema") == SCHEMA]
    return {"politica": policy(), "decisiones": len(decisions), "capturas_de_entrada": len(captures),
            "sin_captura": len(decisions) - len(captures),
            "pendientes": dict(Counter(p for c in captures for p in c.get("pendientes", []))),
            "neto_propio_usd": None, "beneficio_realizado_usd": None,
            "alcance": "entradas para simulacion; neto_modelo_usd sigue siendo un prior de terceros"}
