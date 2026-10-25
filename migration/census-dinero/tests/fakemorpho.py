"""Base falsa con Morpho Blue, oráculos y Multicall3 en memoria. Todo es sintético.

La aritmética del contrato sale de census_dinero.morpho (que se prueba aparte); el ABI de
llamadas, el layout de eventos y el multicall se escriben aquí a mano, sin usar los codificadores
del paquete, para que un error de layout en el paquete no pase inadvertido.
"""

from copy import deepcopy

from census_dinero import morpho as mo
from census_dinero.abi import norm
from census_dinero.keccak import keccak256, selector, topic
from census_dinero.rpc import RpcError

T0 = 1_800_000_000
MORPHO = norm("0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb")
MULTICALL = norm("0xcA11bde05977b3631167028862bE2a173976CA11")
AAVE_ORACLE = norm("0x2Cc0Fc26eD4563A5ce5e8bdcfe1A2878676Ae156")
WETH = norm("0x4200000000000000000000000000000000000006")
USDC = norm("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
AUCTION_ENTRY = norm("0x583dcfef0d240dc80753f0f0b26513fee27d9b77")
BUILDER = norm("0x4200000000000000000000000000000000000011")
PRICE_2000 = 2000 * 10 ** 24            # 1 token de 18 decimales = 2000 USDC (6 decimales), escala de Morpho
LLTV86 = 86 * 10 ** 16
USERS = [norm("0x" + format(0xA0 + i, "02x") * 20) for i in range(12)]
BOTS = [norm("0x" + format(0xB0 + i, "02x") * 20) for i in range(6)]
SIGNERS = [norm("0x" + format(0xC0 + i, "02x") * 20) for i in range(6)]

_SEL = {
    "market": selector("market(bytes32)"), "position": selector("position(bytes32,address)"),
    "params": selector("idToMarketParams(bytes32)"), "price": selector("price()"),
    "decimals": selector("decimals()"), "block_number": selector("getBlockNumber()"),
    "aggregate3": selector("aggregate3((address,bool,bytes)[])"),
    "rate": selector("borrowRateView((address,address,address,address,uint256),"
                     "(uint128,uint128,uint128,uint128,uint128,uint128))"),
    "asset_price": selector("getAssetPrice(address)"),
    "base_feed_1": selector("BASE_FEED_1()"), "base_feed_2": selector("BASE_FEED_2()"),
    "quote_feed_1": selector("QUOTE_FEED_1()"), "quote_feed_2": selector("QUOTE_FEED_2()"), "base_vault": selector("BASE_VAULT()"),
    "round": selector("latestRoundData()"), "description": selector("description()"), "aggregator": selector("aggregator()"),
}
ANSWER_UPDATED = topic("AnswerUpdated(int256,uint256,uint256)")
_T = {n: topic(s) for n, s in mo.EVENT_SIGNATURES.items()}


def word(x):
    return x.to_bytes(32, "big")


def addr_topic(a):
    return "0x" + "0" * 24 + a[2:]


class Revert(Exception):
    pass


class FakeMorpho:
    chain_id = 8453

    def __init__(self, head=5_000, archive_blocks=None, multicall=True, eth_usd=2500, logs_from=None):
        self.head = head
        self.archive_blocks = archive_blocks        # None: archivo completo; n: solo los últimos n bloques
        self.multicall = multicall
        self.logs_from = logs_from                  # None: logs desde el inicio; n: el proveedor solo guarda logs desde el bloque n
        self.eth_usd = eth_usd
        self.markets, self.positions = {}, {}
        self.logs, self.txs, self.receipts, self.headers, self.history = [], {}, {}, {}, {}
        self.hash_salt = {}
        self.faults, self.calls = [], []
        self.token_decimals = {USDC: 6, WETH: 18}
        self.tx_counter = 0
        self.headers[head] = self._header(head, T0 + 2 * head, [])
        self._snap(head)

    # -- escenario ------------------------------------------------------------------------
    def add_market(self, label, price=PRICE_2000, lltv=LLTV86, coll_decimals=18, rate=0, supply=10 ** 13,
                   loan=USDC):
        i = len(self.markets) + 1
        mid = "0x" + keccak256(label.encode()).hex()
        coll = norm("0x" + format(0x1000 + i, "040x"))
        self.token_decimals[coll] = coll_decimals
        self.markets[mid] = {
            "label": label, "params": mo.Params(loan, coll, norm("0x" + format(0x2000 + i, "040x")),
                                                norm("0x" + format(0x3000 + i, "040x")), lltv),
            "price": price, "rate": rate, "oracle_reverts": False,
            "feed": norm("0x" + format(0xFEED00 + i, "040x")), "feed_round": 1, "feed_updated": T0 + 2 * self.head,
            "state": [supply, supply * 10 ** 6, 0, 0, T0 + 2 * self.head, 0]}       # tsa, tss, tba, tbs, last, fee
        self._snap(self.head)                       # el mercado ya existe en el estado del bloque actual
        return mid

    def mine(self, actions=(), dt=2):
        n = self.head + 1
        ts = int(self.headers[self.head]["timestamp"], 16) + dt
        hashes, log_index = [], 0
        for tx_index, act in enumerate(actions):
            kind, args = act[0], act[1:]
            kw = {}
            if args and isinstance(args[-1], dict):
                args, kw = args[:-1], args[-1]
            h = "0x" + format(0xABC000000 + self.tx_counter, "064x")
            self.tx_counter += 1
            logs = getattr(self, "_do_" + kind)(n, ts, h, tx_index, log_index, *args, **kw)
            log_index += len(logs)
            frm = kw.get("sender") or SIGNERS[0]
            to = kw.get("to") or MORPHO
            self.txs[h] = {"hash": h, "from": frm, "to": to, "blockNumber": hex(n), "transactionIndex": hex(tx_index),
                           "gasPrice": hex(kw.get("gas_price", 10 ** 7)), "value": "0x0", "input": "0x"}
            self.receipts[h] = {"transactionHash": h, "status": "0x1", "gasUsed": hex(kw.get("gas_used", 400_000)),
                                "effectiveGasPrice": hex(kw.get("gas_price", 10 ** 7)), "l1Fee": hex(kw.get("l1_fee", 10 ** 12)),
                                "blockNumber": hex(n), "transactionIndex": hex(tx_index), "from": frm, "to": to,
                                "logs": logs}
            hashes.append(h)
        self.head = n
        self.headers[n] = self._header(n, ts, hashes)
        self._snap(n)
        return n

    def reorg(self, block):
        """Cambia el hash del bloque `block`: el siguiente bloque que se mine apuntará al nuevo."""
        self.hash_salt[block] = self.hash_salt.get(block, 0) + 1
        self.headers[block] = dict(self.headers[block], hash=self._hash(block))

    def fail(self, method, times=1, message="internal error", code=-32000, when=None):
        self.faults.append([method, when, {"code": code, "message": message}, times])

    # -- acciones de transacciones ----------------------------------------------------------
    def _accrue(self, mid, ts):
        m = self.markets[mid]
        st = mo.accrue(mo.MarketState(*m["state"]), m["rate"], ts)
        m["state"] = [st.total_supply_assets, st.total_supply_shares, st.total_borrow_assets, st.total_borrow_shares,
                      ts, st.fee]

    def _pos(self, mid, user):
        return self.positions.setdefault((mid, user), [0, 0, 0])

    def _log(self, name, topics, words, n, h, tx_index, log_index):
        return {"address": MORPHO, "topics": [_T[name]] + topics,
                "data": "0x" + "".join(format(x, "064x") for x in words), "blockNumber": hex(n),
                "logIndex": hex(log_index), "transactionHash": h, "transactionIndex": hex(tx_index), "removed": False}

    def _emit(self, lg):
        self.logs.append(lg)
        return [lg]

    def _do_set_price(self, n, ts, h, ti, li, mid, price, **kw):
        m = self.markets[mid]
        m["price"] = price
        m["feed_round"] += 1
        m["feed_updated"] = ts
        lg = {"address": m["feed"], "topics": [ANSWER_UPDATED, "0x" + format(price // 10 ** 18, "064x"), "0x" + format(m["feed_round"], "064x")],
              "data": "0x" + format(ts, "064x"), "blockNumber": hex(n), "logIndex": hex(li), "transactionHash": h,
              "transactionIndex": hex(ti), "removed": False}
        return self._emit(lg)

    def _do_supply_collateral(self, n, ts, h, ti, li, mid, user, assets, **kw):
        caller = kw.get("caller", user)
        self._pos(mid, user)[2] += assets
        return self._emit(self._log("SupplyCollateral", [mid, addr_topic(caller), addr_topic(user)], [assets], n, h, ti, li))

    def _do_withdraw_collateral(self, n, ts, h, ti, li, mid, user, assets, **kw):
        caller = kw.get("caller", user)
        self._pos(mid, user)[2] -= assets
        return self._emit(self._log("WithdrawCollateral", [mid, addr_topic(user), addr_topic(user)],
                                    [int(caller, 16), assets], n, h, ti, li))

    def _do_borrow(self, n, ts, h, ti, li, mid, user, assets, **kw):
        self._accrue(mid, ts)
        st = self.markets[mid]["state"]
        shares = mo.to_shares_up(assets, st[2], st[3])
        st[2] += assets
        st[3] += shares
        self._pos(mid, user)[1] += shares
        caller = kw.get("caller", user)
        return self._emit(self._log("Borrow", [mid, addr_topic(user), addr_topic(user)], [int(caller, 16), assets, shares],
                                    n, h, ti, li))

    def _do_repay(self, n, ts, h, ti, li, mid, user, shares, **kw):
        self._accrue(mid, ts)
        st = self.markets[mid]["state"]
        assets = mo.to_assets_up(shares, st[2], st[3])
        st[2] = max(0, st[2] - assets)
        st[3] -= shares
        self._pos(mid, user)[1] -= shares
        caller = kw.get("caller", user)
        return self._emit(self._log("Repay", [mid, addr_topic(caller), addr_topic(user)], [assets, shares], n, h, ti, li))

    def _do_liquidate(self, n, ts, h, ti, li, mid, caller, borrower, **kw):
        self._accrue(mid, ts)
        m = self.markets[mid]
        st, pos, price, lltv = m["state"], self._pos(mid, borrower), m["price"], m["params"].lltv
        state = mo.MarketState(*st)
        if mo.is_healthy(pos[1], pos[2], price, lltv, state):
            raise AssertionError("la prueba intenta liquidar una posición sana")
        f = mo.lif(lltv)
        if kw.get("seized") is not None:
            seized = kw["seized"]
            quoted = mo.mul_div_up(seized, price, mo.ORACLE_PRICE_SCALE)
            shares = mo.to_shares_up(mo.w_div_up(quoted, f), st[2], st[3])
        else:
            shares = kw.get("repaid_shares", pos[1])
            seized = mo.mul_div_down(mo.w_mul_down(mo.to_assets_down(shares, st[2], st[3]), f), mo.ORACLE_PRICE_SCALE, price)
        if seized > pos[2] or shares > pos[1]:
            raise AssertionError("la prueba intenta embargar o repagar más de lo que hay")
        repaid = mo.to_assets_up(shares, st[2], st[3])
        pos[1] -= shares
        st[3] -= shares
        st[2] = max(0, st[2] - repaid)
        pos[2] -= seized
        bad_s = bad_a = 0
        if pos[2] == 0:
            bad_s = pos[1]
            bad_a = min(st[2], mo.to_assets_up(bad_s, st[2], st[3]))
            st[2] -= bad_a
            st[0] -= bad_a
            st[3] -= bad_s
            pos[1] = 0
        return self._emit(self._log("Liquidate", [mid, addr_topic(caller), addr_topic(borrower)],
                                    [repaid, shares, seized, bad_a, bad_s], n, h, ti, li))

    def _do_noop(self, n, ts, h, ti, li, *a, **kw):
        return []

    # -- cadena -----------------------------------------------------------------------------
    def _hash(self, n):
        return "0x" + format(n * 1_000_003 + self.hash_salt.get(n, 0) * 7_777_777, "064x")

    def _bloom(self, n):
        """logsBloom del bloque n (yellow paper): cada dirección y cada topic activa 3 bits de un entero de 2048 bits."""
        value = 0
        for lg in self.logs:
            if int(lg["blockNumber"], 16) != n:
                continue
            for item in [lg["address"]] + list(lg["topics"]):
                h = keccak256(bytes.fromhex(item[2:]))
                for i in (0, 2, 4):
                    value |= 1 << (int.from_bytes(h[i:i + 2], "big") % 2048)
        return "0x" + value.to_bytes(256, "big").hex()

    def _header(self, n, ts, hashes):
        return {"number": hex(n), "hash": self._hash(n), "parentHash": self.headers[n - 1]["hash"] if n - 1 in self.headers
                else self._hash(n - 1), "timestamp": hex(ts), "baseFeePerGas": hex(5_000_000), "miner": BUILDER,
                "transactions": list(hashes), "logsBloom": self._bloom(n)}

    def _snap(self, n):
        self.history[n] = {"markets": deepcopy({k: (v["state"], v["price"], v["rate"], v["oracle_reverts"])
                                                 for k, v in self.markets.items()}),
                           "positions": deepcopy(self.positions), "ts": int(self.headers[n]["timestamp"], 16),
                           "feeds": {k: (v["feed_round"], v["feed_updated"]) for k, v in self.markets.items()}}

    def _state_at(self, tag):
        n = self.head if tag == "latest" else int(tag, 16)
        if n > self.head:
            raise RpcError("header not found", -32000)
        if self.archive_blocks is not None and self.head - n > self.archive_blocks:
            raise RpcError("missing trie node 0xabc (path ) state is not available", -32000)
        if n not in self.history:
            raise RpcError("header not found", -32000)
        return n, self.history[n]

    # -- eth_call ---------------------------------------------------------------------------
    def _eth_call(self, to, data, tag):
        n, snap = self._state_at(tag)
        return "0x" + self._exec(norm(to), bytes.fromhex(data[2:]), n, snap).hex()

    def _exec(self, to, data, n, snap):
        sel, args = "0x" + data[:4].hex(), data[4:]
        if to == MULTICALL:
            if not self.multicall:
                return b""                                          # sin código: devuelve vacío
            if sel == _SEL["block_number"]:
                return word(n)
            if sel == _SEL["aggregate3"]:
                return self._aggregate3(args, n, snap)
            raise Revert()
        if to == MORPHO:
            mid = "0x" + args[:32].hex()
            if sel == _SEL["market"]:
                if mid not in snap["markets"]:
                    return b"\0" * 192
                return b"".join(word(x) for x in snap["markets"][mid][0])
            if sel == _SEL["position"]:
                user = norm("0x" + args[44:64].hex())
                return b"".join(word(x) for x in snap["positions"].get((mid, user), [0, 0, 0]))
            if sel == _SEL["params"]:
                if mid not in self.markets:
                    return b"\0" * 160
                p = self.markets[mid]["params"]
                return b"".join(word(int(x, 16)) for x in (p.loan, p.collateral, p.oracle, p.irm)) + word(p.lltv)
            raise Revert()
        for mid, m in self.markets.items():
            if to == m["params"].oracle and sel == _SEL["base_feed_1"]:
                return word(int(m["feed"], 16))
            if to == m["params"].oracle and sel in (_SEL["base_feed_2"], _SEL["quote_feed_1"], _SEL["quote_feed_2"], _SEL["base_vault"]):
                return word(0)
            if to == m["feed"]:
                rnd, upd = snap["feeds"][mid]
                if sel == _SEL["round"]:
                    return word(rnd) + word(snap["markets"][mid][1] // 10 ** 18) + word(upd) + word(upd) + word(rnd)
                if sel == _SEL["description"]:
                    text = f"{m['label']} / USD".encode()
                    return word(32) + word(len(text)) + text.ljust(32 * ((len(text) + 31) // 32), b"\0")
                if sel == _SEL["decimals"]:
                    return word(8)
                if sel == _SEL["aggregator"]:
                    return word(int(m["feed"], 16) + 1)
            if to == m["params"].oracle and sel == _SEL["price"]:
                if snap["markets"][mid][3]:
                    raise Revert()
                return word(snap["markets"][mid][1])
            if to == m["params"].irm and sel == _SEL["rate"]:
                return word(snap["markets"][mid][2])
        if sel == _SEL["decimals"] and to in self.token_decimals:
            return word(self.token_decimals[to])
        if to == AAVE_ORACLE and sel == _SEL["asset_price"]:
            return word(self.eth_usd * 10 ** 8)
        return b""

    def _aggregate3(self, b, n, snap):
        arr = int.from_bytes(b[0:32], "big")
        count = int.from_bytes(b[arr:arr + 32], "big")
        base = arr + 32
        results = []
        for i in range(count):
            t = base + int.from_bytes(b[base + 32 * i:base + 32 * i + 32], "big")
            target = norm("0x" + b[t + 12:t + 32].hex())
            allow = int.from_bytes(b[t + 32:t + 64], "big")
            boff = int.from_bytes(b[t + 64:t + 96], "big")
            blen = int.from_bytes(b[t + boff:t + boff + 32], "big")
            call = b[t + boff + 32:t + boff + 32 + blen]
            try:
                results.append((True, self._exec(target, call, n, snap)))
            except Revert:
                if not allow:
                    raise
                results.append((False, b"\x08\xc3\x79\xa0"))
        tuples = [word(1 if ok else 0) + word(0x40) + word(len(d)) + d + b"\0" * ((-len(d)) % 32) for ok, d in results]
        head, off = b"", len(tuples) * 32
        for t_ in tuples:
            head += word(off)
            off += len(t_)
        return word(0x20) + word(len(tuples)) + head + b"".join(tuples)

    # -- eth_getLogs ------------------------------------------------------------------------
    def _get_logs(self, flt):
        if "blockHash" in flt:
            found = [n for n, h in self.headers.items() if h["hash"] == flt["blockHash"]]
            if not found:
                raise RpcError("unknown block", -32000)
            lo = hi = found[0]
        else:
            lo, hi = int(flt["fromBlock"], 16), int(flt["toBlock"], 16)
        if hi > self.head:
            raise RpcError("block range extends beyond current head block", -32000)
        if self.logs_from is not None and lo < self.logs_from:
            raise RpcError(f"pruned history unavailable: requested {lo}, earliest available {self.logs_from}", -32000)
        addrs = flt.get("address")
        addrs = None if addrs is None else {norm(a) for a in (addrs if isinstance(addrs, list) else [addrs])}
        topics = flt.get("topics") or []

        def match(lg):
            for i, want in enumerate(topics):
                if want is None:
                    continue
                want = [x.lower() for x in (want if isinstance(want, list) else [want])]
                if i >= len(lg["topics"]) or lg["topics"][i].lower() not in want:
                    return False
            return True
        return [lg for lg in self.logs if lo <= int(lg["blockNumber"], 16) <= hi
                and (addrs is None or norm(lg["address"]) in addrs) and match(lg)]

    # -- transporte --------------------------------------------------------------------------
    def __call__(self, url, payload, timeout):
        m, p = payload["method"], payload["params"]
        self.calls.append((m, url))
        for f in self.faults:
            if f[0] == m and f[3] > 0 and (f[1] is None or f[1](p)):
                f[3] -= 1
                return {"jsonrpc": "2.0", "id": payload["id"], "error": dict(f[2])}
        try:
            if m == "eth_chainId":
                res = hex(self.chain_id)
            elif m == "eth_blockNumber":
                res = hex(self.head)
            elif m == "eth_getBlockByNumber":
                tag = p[0]
                n = self.head if tag in ("latest", "finalized") else int(tag, 16)
                res = self.headers.get(n)
            elif m == "eth_getLogs":
                res = self._get_logs(p[0])
            elif m == "eth_call":
                res = self._eth_call(p[0]["to"], p[0]["data"], p[1])
            elif m == "eth_getTransactionByHash":
                res = self.txs.get(p[0])
            elif m == "eth_getTransactionReceipt":
                res = self.receipts.get(p[0])
            elif m == "eth_getCode":
                res = "0x"
            else:
                raise AssertionError(f"método sin implementar en la cadena falsa: {m}")
        except Revert:
            return {"jsonrpc": "2.0", "id": payload["id"], "error": {"code": 3, "message": "execution reverted"}}
        except RpcError as e:
            return {"jsonrpc": "2.0", "id": payload["id"], "error": {"code": e.code or -32000, "message": str(e)}}
        return {"jsonrpc": "2.0", "id": payload["id"], "result": res}
