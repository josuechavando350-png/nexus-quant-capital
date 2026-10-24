"""Cadena falsa en memoria para probar el census sin red. Todos los datos son sintéticos."""

from census_dinero.abi import encode_address, norm, strip0x
from census_dinero.config import (AAVE_LIQUIDATION_TOPIC, ANSWER_UPDATED_TOPIC, ERC20_TRANSFER_TOPIC,
                                  MORPHO_LIQUIDATE_TOPIC, SEL)
from census_dinero.keccak import topic

WITHDRAWAL_TOPIC = topic("Withdrawal(address,uint256)")
from census_dinero.rpc import RpcError

T0 = 1_700_000_000
WETH = norm("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2")
USDC = norm("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")
WSTETH = norm("0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0")
AAVE_POOL = norm("0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2")
AAVE_ORACLE = norm("0x54586bE62E3c3580375aE3723C145253060Ca0C2")
MORPHO = norm("0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb")
BUILDER = norm("0x" + "b1" * 20)
BOT_A = norm("0x" + "a1" * 20)
BOT_B = norm("0x" + "a2" * 20)
EOA_A = norm("0x" + "e1" * 20)
EOA_B = norm("0x" + "e2" * 20)
BORROWER = norm("0x" + "cc" * 20)
P_ETH, AGG_ETH = norm("0x" + "11" * 20), norm("0x" + "12" * 20)
P_USDC, AGG_USDC = norm("0x" + "21" * 20), norm("0x" + "22" * 20)
CAPO_WSTETH = norm("0x" + "31" * 20)
MORPHO_ORACLE = norm("0x" + "41" * 20)
MARKET_ID = "0x" + "ab" * 32
EOA_BENEF = norm("0x" + "be" * 20)
AUSDC, AWETH = norm("0x" + "51" * 20), norm("0x" + "52" * 20)
POOLX, POOLY = norm("0x" + "61" * 20), norm("0x" + "62" * 20)
AUCTION = norm("0x" + "71" * 20)
EOAS = {EOA_A, EOA_B, EOA_BENEF, BORROWER}
GWEI = 10 ** 9


def w(x):
    return format(x, "064x")


def th(i):
    return "0x" + format(i, "064x")


class FakeChain:
    def __init__(self, head=20_100, log_range_limit=None, archive=True, traces=True, chain_id=1):
        self.head = head
        self.log_range_limit = log_range_limit
        self.archive = archive
        self.traces = traces
        self.chain_id = chain_id
        self.logs = []
        self.txs = {}
        self.receipts = {}
        self.traces_by_tx = {}
        self.calls = []
        self._build()

    # -- escenario ----------------------------------------------------------------
    def _log(self, address, topics, data, block, log_index, tx, tx_index=0):
        self.logs.append({"address": address, "topics": topics, "data": "0x" + data,
                          "blockNumber": hex(block), "logIndex": hex(log_index), "transactionHash": tx,
                          "transactionIndex": hex(tx_index), "removed": False})

    def _tx(self, h, frm, to, block, gas_used, eff_gwei, logs_extra=()):
        self.txs[h] = {"hash": h, "from": frm, "to": to, "value": "0x0", "blockNumber": hex(block)}
        self.receipts[h] = {"transactionHash": h, "status": "0x1", "gasUsed": hex(gas_used),
                            "effectiveGasPrice": hex(eff_gwei * GWEI), "logs": list(logs_extra)}

    def _build(self):
        # Actualizaciones de oráculo: ETH en 19990 (log 2), USDC en 19000.
        self._log(AGG_ETH, [ANSWER_UPDATED_TOPIC, th(3000), th(1)], w(T0), 19990, 2, th(0xF1), 0)
        self._log(AGG_USDC, [ANSWER_UPDATED_TOPIC, th(1), th(1)], w(T0), 19000, 0, th(0xF2), 0)
        self._log(AGG_ETH, [ANSWER_UPDATED_TOPIC, th(3000), th(2)], w(T0), 19998, 0, th(0xF3), 0)

        # tx A: Aave WETH colateral / USDC deuda, 1000 USDC -> 0.35 WETH. Mismo bloque que la actualización.
        txa = th(0xA)
        self._log(AAVE_POOL, [AAVE_LIQUIDATION_TOPIC, "0x" + encode_address(WETH), "0x" + encode_address(USDC),
                              "0x" + encode_address(BORROWER)],
                  w(1000 * 10 ** 6) + w(35 * 10 ** 16) + encode_address(BOT_A) + w(0), 19990, 5, txa, 1)
        self._tx(txa, EOA_A, BOT_A, 19990, 300_000, 12)
        self.traces_by_tx[txa] = {"type": "CALL", "from": EOA_A, "to": BOT_A, "value": "0x0", "calls": [
            {"type": "CALL", "from": BOT_A, "to": BUILDER, "value": hex(5 * 10 ** 15)},
            {"type": "CALL", "from": BOT_A, "to": BUILDER, "value": hex(10 ** 18), "error": "execution reverted"},
            {"type": "DELEGATECALL", "from": BOT_A, "to": BUILDER, "value": hex(10 ** 18)},
        ]}

        # tx B: Morpho, 10,000 USDC repagados, lltv 86%.
        txb = th(0xB)
        self._log(MORPHO, [MORPHO_LIQUIDATE_TOPIC, MARKET_ID, "0x" + encode_address(BOT_B),
                           "0x" + encode_address(BORROWER)],
                  w(10_000 * 10 ** 6) + w(123) + w(4 * 10 ** 18) + w(0) + w(0), 19995, 3, txb, 0)
        self._tx(txb, EOA_B, BOT_B, 19995, 400_000, 10)
        self.traces_by_tx[txb] = {"type": "CALL", "from": EOA_B, "to": BOT_B, "value": "0x0", "calls": []}

        # tx C: dos liquidaciones Aave wstETH/USDC en la misma transacción.
        txc = th(0xC)
        for li, debt in ((7, 300), (8, 100)):
            seized = int(debt * 1.05 / 3500 * 10 ** 18)
            self._log(AAVE_POOL, [AAVE_LIQUIDATION_TOPIC, "0x" + encode_address(WSTETH), "0x" + encode_address(USDC),
                                  "0x" + encode_address(BORROWER)],
                      w(debt * 10 ** 6) + w(seized) + encode_address(BOT_A) + w(1), 19999, li, txc, 2)
        self._tx(txc, EOA_A, BOT_A, 19999, 500_000, 11)
        self.traces_by_tx[txc] = {"type": "CALL", "from": EOA_A, "to": BOT_A, "value": "0x0", "calls": []}

        # tx D: liquidación con flash loan, venta del colateral, puja en ETH a una subasta y ganancia a un EOA.
        txd = th(0xD)
        self._log(AAVE_POOL, [AAVE_LIQUIDATION_TOPIC, "0x" + encode_address(WETH), "0x" + encode_address(USDC),
                              "0x" + encode_address(BORROWER)],
                  w(2000 * 10 ** 6) + w(7 * 10 ** 17) + encode_address(BOT_A) + w(0), 19997, 4, txd, 3)
        bid = 80 * 10 ** 18 // 3000

        def tr(token, frm, to, amt):
            return {"address": token, "topics": [ERC20_TRANSFER_TOPIC, "0x" + encode_address(frm),
                                                 "0x" + encode_address(to)], "data": "0x" + w(amt)}
        logs = [
            tr(USDC, MORPHO, BOT_A, 2000 * 10 ** 6),
            tr(USDC, BOT_A, AUSDC, 2000 * 10 ** 6),
            tr(WETH, AWETH, BOT_A, 7 * 10 ** 17),
            tr(WETH, BOT_A, POOLX, 7 * 10 ** 17),
            tr(USDC, POOLX, BOT_A, 2095 * 10 ** 6),
            tr(USDC, BOT_A, MORPHO, 2000 * 10 ** 6),
            tr(USDC, BOT_A, EOA_BENEF, 15 * 10 ** 6),
            tr(USDC, BOT_A, POOLY, 80 * 10 ** 6),
            tr(WETH, POOLY, BOT_A, bid),
            {"address": WETH, "topics": [WITHDRAWAL_TOPIC, "0x" + encode_address(BOT_A)], "data": "0x" + w(bid)},
        ]
        self._tx(txd, EOA_A, BOT_A, 19997, 350_000, 12, logs_extra=logs)
        self.traces_by_tx[txd] = {"type": "CALL", "from": EOA_A, "to": BOT_A, "value": "0x0", "calls": [
            {"type": "CALL", "from": WETH, "to": BOT_A, "value": hex(bid)},
            {"type": "CALL", "from": BOT_A, "to": AUCTION, "value": hex(bid)},
        ]}

    # -- respuestas -----------------------------------------------------------------
    def block(self, n):
        return {"number": hex(n), "timestamp": hex(T0 + 12 * n), "baseFeePerGas": hex(10 * GWEI),
                "miner": BUILDER, "transactions": [th(0xA), th(0xB)]}

    def eth_call(self, to, data, tag):
        to = norm(to)
        sel, args = data[:10], strip0x(data)[8:]
        if tag != "latest" and not self.archive:
            raise RpcError("missing trie node")
        prices = {WETH: 3000, USDC: 1, WSTETH: 3500}
        if to == AAVE_ORACLE:
            if sel == SEL["BASE_CURRENCY_UNIT"]:
                return "0x" + w(10 ** 8)
            asset = norm("0x" + args[-40:])
            if sel == SEL["getAssetPrice"]:
                return "0x" + w(prices.get(asset, 0) * 10 ** 8)
            if sel == SEL["getSourceOfAsset"]:
                return "0x" + encode_address({WETH: P_ETH, USDC: P_USDC, WSTETH: CAPO_WSTETH}.get(asset, "0x0"))
        if to == P_ETH and sel == SEL["aggregator"]:
            return "0x" + encode_address(AGG_ETH)
        if to == P_USDC and sel == SEL["aggregator"]:
            return "0x" + encode_address(AGG_USDC)
        if to == CAPO_WSTETH:
            if sel == SEL["BASE_TO_USD_AGGREGATOR"]:
                return "0x" + encode_address(P_ETH)
            if sel == SEL["aggregator"]:
                raise RpcError("execution reverted", 3)
            return "0x"
        if to == MORPHO and sel == SEL["idToMarketParams"]:
            return "0x" + encode_address(USDC) + encode_address(WSTETH) + encode_address(MORPHO_ORACLE) \
                + encode_address("0x" + "99" * 20) + w(86 * 10 ** 16)
        if to == MORPHO_ORACLE:
            if sel == SEL["BASE_FEED_1"]:
                return "0x" + encode_address(P_ETH)
            if sel in (SEL["BASE_FEED_2"], SEL["QUOTE_FEED_1"], SEL["QUOTE_FEED_2"]):
                return "0x" + w(0)
        tokens = {WETH: (18, "WETH"), USDC: (6, "USDC"), WSTETH: (18, "wstETH")}
        if to in tokens:
            if sel == SEL["decimals"]:
                return "0x" + w(tokens[to][0])
            if sel == SEL["symbol"]:
                s = tokens[to][1].encode().hex()
                return "0x" + w(32) + w(len(tokens[to][1])) + s.ljust(64, "0")
        raise RpcError("execution reverted", 3)

    def get_logs(self, flt):
        lo, hi = int(flt["fromBlock"], 16), int(flt["toBlock"], 16)
        if self.log_range_limit and hi - lo + 1 > self.log_range_limit:
            raise RpcError("query exceeds max block range")
        addrs = flt.get("address")
        addrs = None if addrs is None else {norm(a) for a in (addrs if isinstance(addrs, list) else [addrs])}
        t0 = flt["topics"][0] if flt.get("topics") else None
        t0 = None if t0 is None else {x.lower() for x in (t0 if isinstance(t0, list) else [t0])}
        return [lg for lg in self.logs
                if lo <= int(lg["blockNumber"], 16) <= hi
                and (addrs is None or norm(lg["address"]) in addrs)
                and (t0 is None or lg["topics"][0].lower() in t0)]

    def __call__(self, url, payload, timeout):
        m, p = payload["method"], payload["params"]
        self.calls.append(m)
        try:
            if m == "eth_chainId":
                res = hex(self.chain_id)
            elif m == "eth_blockNumber":
                res = hex(self.head)
            elif m == "eth_getBlockByNumber":
                n = self.head - 10 if p[0] == "finalized" else int(p[0], 16)
                res = self.block(n)
            elif m == "eth_getLogs":
                res = self.get_logs(p[0])
            elif m == "eth_call":
                res = self.eth_call(p[0]["to"], p[0]["data"], p[1])
            elif m == "eth_getCode":
                res = "0x" if norm(p[0]) in EOAS else "0x6080604052"
            elif m == "eth_getTransactionByHash":
                res = self.txs.get(p[0])
            elif m == "eth_getTransactionReceipt":
                res = self.receipts.get(p[0])
            elif m == "debug_traceTransaction":
                if not self.traces:
                    return {"jsonrpc": "2.0", "id": payload["id"], "error": {"code": -32601, "message": "method not found"}}
                res = self.traces_by_tx[p[0]]
            elif m == "trace_transaction":
                return {"jsonrpc": "2.0", "id": payload["id"], "error": {"code": -32601, "message": "method not found"}}
            else:
                raise AssertionError(m)
        except RpcError as e:
            return {"jsonrpc": "2.0", "id": payload["id"], "error": {"code": e.code or -32000, "message": str(e)}}
        return {"jsonrpc": "2.0", "id": payload["id"], "result": res}
