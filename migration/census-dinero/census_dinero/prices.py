"""Precios en USD: oráculo de Aave en el bloque exacto y, si no hay nodo de archivo, DefiLlama."""

import threading

from .abi import encode_address, norm, words
from .config import SEL
from .rpc import CallReverted, RpcError
from .web import WebError

LLAMA = "https://coins.llama.fi/prices/historical/{ts}/{coins}?searchWidth=4h"


class Prices:
    def __init__(self, rpc, chain, web, *, llama_url=LLAMA):
        self.rpc = rpc
        self.chain = chain
        self.web = web
        self.llama_url = llama_url
        self.core_oracle = chain.aave[0].oracle if chain.aave else None
        self.lock = threading.Lock()
        self.units = {}
        self.listed = {}
        self.cache = {}
        self.llama_cache = {}
        self.archive_ok = 0
        self.archive_fail = 0
        self.archive_disabled = False
        self.stats = {"oraculo": 0, "defillama": 0, "sin_precio": 0}

    # -- oráculo de Aave -------------------------------------------------------
    def oracle_unit(self, oracle):
        with self.lock:
            if oracle in self.units:
                return self.units[oracle]
        try:
            unit = words(self.rpc.eth_call(oracle, SEL["BASE_CURRENCY_UNIT"]))[0] or 10 ** 8
        except (RpcError, ValueError, IndexError):
            unit = 10 ** 8
        with self.lock:
            self.units[oracle] = unit
        return unit

    def is_listed(self, oracle, asset):
        key = (oracle, norm(asset))
        with self.lock:
            if key in self.listed:
                return self.listed[key]
        try:
            src = words(self.rpc.eth_call(oracle, SEL["getSourceOfAsset"] + encode_address(asset)))[0]
            ok = src != 0
        except (RpcError, ValueError, IndexError):
            ok = False
        with self.lock:
            self.listed[key] = ok
        return ok

    def aave_price(self, oracle, asset, block):
        """Precio USD que el propio protocolo usó en ese bloque, o None."""
        if self.archive_disabled or not oracle:
            return None
        key = (oracle, norm(asset), block)
        with self.lock:
            if key in self.cache:
                return self.cache[key]
        price = None
        try:
            raw = words(self.rpc.eth_call(oracle, SEL["getAssetPrice"] + encode_address(asset), block))[0]
            if raw:
                price = raw / self.oracle_unit(oracle)
            with self.lock:
                self.archive_ok += 1
        except CallReverted:
            price = None
        except (RpcError, ValueError, IndexError):
            with self.lock:
                self.archive_fail += 1
                if self.archive_ok == 0 and self.archive_fail >= 8:
                    self.archive_disabled = True
        with self.lock:
            self.cache[key] = price
        return price

    # -- DefiLlama ---------------------------------------------------------------
    def llama(self, coin, ts):
        bucket = ts - ts % 300
        key = (coin, bucket)
        with self.lock:
            if key in self.llama_cache:
                return self.llama_cache[key]
        price = None
        try:
            data = self.web.get(self.llama_url.format(ts=bucket, coins=coin))
            entry = (data.get("coins") or {}).get(coin)
            if entry is None:
                # DefiLlama a veces normaliza las mayúsculas de la dirección.
                for k, v in (data.get("coins") or {}).items():
                    if k.lower() == coin.lower():
                        entry = v
                        break
            if entry and entry.get("price") is not None:
                price = float(entry["price"])
        except WebError:
            price = None
        with self.lock:
            self.llama_cache[key] = price
        return price

    # -- API de alto nivel -------------------------------------------------------
    def token_usd(self, asset, block, ts, oracle=None):
        """Devuelve (precio, fuente). Prioriza el oráculo del mercado en el bloque exacto."""
        oracle = oracle or self.core_oracle
        if oracle and (oracle != self.core_oracle or self.is_listed(oracle, asset)):
            p = self.aave_price(oracle, asset, block)
            if p:
                self.stats["oraculo"] += 1
                return p, "oraculo@bloque"
        if oracle != self.core_oracle and self.core_oracle and self.is_listed(self.core_oracle, asset):
            p = self.aave_price(self.core_oracle, asset, block)
            if p:
                self.stats["oraculo"] += 1
                return p, "oraculo@bloque"
        p = self.llama(f"{self.chain.llama}:{norm(asset)}", ts)
        if p:
            self.stats["defillama"] += 1
            return p, "mercado_defillama"
        self.stats["sin_precio"] += 1
        return None, "sin_precio"

    def eth_usd(self, block, ts):
        p, src = self.token_usd(self.chain.weth, block, ts)
        if p:
            return p, src
        p = self.llama("coingecko:ethereum", ts)
        return (p, "mercado_defillama") if p else (None, "sin_precio")
