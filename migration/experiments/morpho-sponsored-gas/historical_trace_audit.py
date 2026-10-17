"""Offline reconciliation of case B's indexer trace, never a historical fork.

Checks complete trace-tree shape, observed integer arithmetic and cash flows.
The input provider is NOT a consensus proof or independent replay. Evidence read
inside the winner's transaction is used for parity only, not a pre-winner quote.
"""
import json
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from evm_hash import keccak256
from morpho_interest_math import MarketState, accrue
from morpho_liquidation_math import PostAccrualWitness, calculate

TX = "0x46300e9614c547118ecdd524bc7218208088cc4ae9e5bd534e62055d38f9925b"
BLOCK_HASH = "0x5d499e63c5d119293a906036f369d8d75f9560618efec0ff916e4fefa33dfda8"
PARENT_HASH = "0xf57a30121eac97b983cad86fcb3107787a9d400ca4d69d5a96a4b1b618ac65dc"
MORPHO = "0xbbbbbbbbbb9cc5e90e3b3af64bdaf62c37eeffcb"
WETH = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
EXECUTOR = "0x5ac9bc14376bf2727c6211960cf3cec1e2f295bd"
SENDER = "0xd9fffdf0c4b18fb7e225da15b2af9f88e55676c3"


def uints(data: str, count: int) -> list[int]:
    if not isinstance(data, str) or len(data) != 2 + 64 * count or not data.startswith("0x"):
        raise ValueError("invalid fixed ABI words")
    if any(c not in "0123456789abcdefABCDEF" for c in data[2:]):
        raise ValueError("invalid ABI hex")
    return [int(data[2+i*64:2+(i+1)*64], 16) for i in range(count)]


def trace_tree(envelope: dict) -> dict[tuple, dict]:
    if envelope.get("pagination") is not None:
        raise ValueError("trace pagination incomplete")
    traces = envelope["data"]["items"]
    by_path = {}
    for t in traces:
        path = t["traceAddress"]
        if not isinstance(path, list) or any(type(x) is not int or x < 0 for x in path):
            raise ValueError("invalid trace path")
        key = tuple(path)
        if key in by_path or t.get("error") or "result" not in t or t.get("type") != "call":
            raise ValueError("duplicate, failed or unsupported trace")
        by_path[key] = t
    if () not in by_path:
        raise ValueError("missing trace root")
    for path, t in by_path.items():
        if path and path[:-1] not in by_path:
            raise ValueError("orphan trace")
        children = {p[-1] for p in by_path if len(p) == len(path)+1 and p[:-1] == path}
        if type(t["subtraces"]) is not int or t["subtraces"] < 0 or children != set(range(t["subtraces"])):
            raise ValueError("missing or reordered child trace")
    return by_path


def inspect(trace: dict, block: dict, receipt: dict) -> dict:
    # These are provenance consistency checks, not cryptographic authentication.
    expected_requests = (
        (trace, {"method":"direct_api_call", "chain_id":"1",
                 "endpoint_path":f"/api/v2/transactions/{TX}/raw-trace"}),
        (receipt, {"method":"get_transaction_info", "chain_id":"1", "transaction_hash":TX}),
        (block, {"method":"get_block_info", "chain_id":"1", "number_or_hash":"26190955"}),
    )
    for envelope, expected in expected_requests:
        if envelope.get("request") != expected:
            raise ValueError("evidence request identity mismatch")
    tree = trace_tree(trace)
    b, r = block["data"]["block_details"], receipt["data"]
    if (b["hash"] != BLOCK_HASH or b["parent_hash"] != PARENT_HASH or
        b["height"] != 26190955 or r["block_number"] != b["height"]):
        raise ValueError("historical block mismatch")
    if r["position"] != 1 or r["result"] != "success":
        raise ValueError("wrong transaction boundary or failed receipt")
    root = tree[()]["action"]
    if root["from"].lower() != SENDER or root["to"].lower() != EXECUTOR:
        raise ValueError("wrong trace actor")
    if r["from"].lower() != SENDER or r["to"].lower() != EXECUTOR:
        raise ValueError("wrong receipt actor")
    if (not root["input"].startswith(r["raw_input"]) or
        (not r.get("raw_input_truncated") and root["input"] != r["raw_input"])):
        raise ValueError("trace input differs from receipt input")
    if int(r["gas_used"]) * int(r["gas_price"]) != int(r["fee"]["value"]):
        raise ValueError("receipt gas mismatch")

    def call(path, to, signature):
        t = tree[tuple(path)]
        selector = "0x" + keccak256(signature.encode())[:4].hex()
        if t["action"]["to"].lower() != to.lower() or not t["action"]["input"].startswith(selector):
            raise ValueError("trace call identity mismatch")
        return t

    liq = call([0,1,3], MORPHO,
               "liquidate((address,address,address,address,uint256),address,uint256,uint256,bytes)")
    inp = liq["action"]["input"]
    args = uints("0x" + inp[10:10+9*64], 9)
    if any(a >= 2**160 for a in args[:4]) or args[5] >= 2**160 or args[6] != 0 or args[8] != 288:
        raise ValueError("unsupported liquidation ABI")
    length = uints("0x" + inp[10+9*64:10+10*64], 1)[0]
    if length == 0 or len(inp) != 10+10*64+((length+31)//32)*64:
        raise ValueError("missing or truncated original callback")
    addresses = ["0x" + n.to_bytes(20, "big").hex() for n in args[:4]]
    if addresses[0] != WETH:
        raise ValueError("not the WETH debt case")
    irm = call([0,1,3,0], addresses[3],
               "borrowRate((address,address,address,address,uint256),(uint128,uint128,uint128,uint128,uint128,uint128))")
    irm_args = uints("0x" + irm["action"]["input"][10:], 11)
    if irm_args[:5] != args[:5]:
        raise ValueError("IRM market mismatch")
    pre_market = MarketState(*irm_args[5:])
    rate = uints(irm["result"]["output"], 1)[0]
    timestamp = int(datetime.fromisoformat(b["timestamp"].replace("Z", "+00:00")).timestamp())
    accrued = accrue(pre_market, timestamp, rate)
    pos = call([0,0], MORPHO, "position(bytes32,address)")
    position_args = uints("0x" + pos["action"]["input"][10:], 2)
    market_id = keccak256(b"".join(n.to_bytes(32,"big") for n in args[:5]))
    if position_args != [int.from_bytes(market_id,"big"), args[5]]:
        raise ValueError("position market/borrower mismatch")
    position = uints(pos["result"]["output"], 3)
    oracle = call([0,1,3,1], addresses[2], "price()")
    price = uints(oracle["result"]["output"], 1)[0]
    witness = PostAccrualWitness(accrued.market.total_borrow_assets,
                                accrued.market.total_borrow_shares, position[1], position[2], price, args[4])
    quote = calculate(witness, args[7])
    if uints(liq["result"]["output"], 2) != [quote.seized_assets, quote.repaid_assets]:
        raise ValueError("model disagrees with Morpho return")

    native_flows = []
    for path, t in tree.items():
        a = t["action"]
        # DELEGATECALL value is inherited context, never a second transfer.
        if a["callType"] == "call" and int(a["value"],16):
            native_flows.append({"path": list(path), "from": a["from"].lower(),
                                 "to": a["to"].lower(), "wei": int(a["value"],16)})
    coinbase = b["miner"]["hash"].lower()
    native_delta = sum(f["wei"]*((f["to"]==EXECUTOR)-(f["from"]==EXECUTOR)) for f in native_flows)
    coinbase_paid = sum(f["wei"] for f in native_flows if f["from"]==EXECUTOR and f["to"]==coinbase)
    deposits = sum(f["wei"] for f in native_flows if f["from"]==EXECUTOR and f["to"]==WETH)
    withdrawals = sum(f["wei"] for f in native_flows if f["from"]==WETH and f["to"]==EXECUTOR)
    before = call([0,1,0], WETH, "balanceOf(address)")
    after = call([0,1,4], WETH, "balanceOf(address)")
    for item in (before, after):
        if uints("0x"+item["action"]["input"][10:],1)[0] != int(EXECUTOR,16):
            raise ValueError("WETH balance belongs to another account")
    initial_weth = uints(before["result"]["output"],1)[0]
    before_withdrawal = uints(after["result"]["output"],1)[0]
    if initial_weth + deposits - quote.repaid_assets != before_withdrawal:
        raise ValueError("WETH before-withdrawal reconciliation failed")
    residual = deposits - quote.repaid_assets - withdrawals
    if withdrawals != coinbase_paid or native_delta != 0:
        raise ValueError("native flows differ from observed case B")

    # Cross-check normalized indexer token movements against direct token calls.
    # WETH mint/burn rows may be normalized from Deposit/Withdrawal events;
    # they are not asserted to be literal ERC-20 Transfer logs.
    if r.get("token_transfers_overflow") is not False:
        raise ValueError("incomplete token movement list")
    actual_transfers = []
    for t in tree.values():
        a = t["action"]
        if a["callType"] != "call":
            continue
        selector, payload = a["input"][:10], "0x" + a["input"][10:]
        if selector == "0xa9059cbb":
            to, amount = uints(payload, 2)
            source = a["from"].lower()
        elif selector == "0x23b872dd":
            source_int, to, amount = uints(payload, 3)
            if source_int >= 2**160:
                raise ValueError("noncanonical transfer source")
            source = "0x" + source_int.to_bytes(20, "big").hex()
        else:
            continue
        if to >= 2**160:
            raise ValueError("noncanonical transfer recipient")
        actual_transfers.append((a["to"].lower(), source, "0x" + to.to_bytes(20, "big").hex(), amount))
    expected_transfers = Counter([
        (addresses[1], MORPHO, EXECUTOR, quote.seized_assets),
        (addresses[1], EXECUTOR, "0x52aa899454998be5b000ad077a46bbe360f4e497", quote.seized_assets),
        (WETH, EXECUTOR, MORPHO, quote.repaid_assets),
    ])
    if Counter(actual_transfers) != expected_transfers:
        raise ValueError("unsupported token flows outside case B ledger")
    receipt_transfers = []
    normalized = Counter()
    for t in r["token_transfers"]:
        edge = (t["token"]["address_hash"].lower(), t["from"].lower(), t["to"].lower(), int(t["total"]["value"]))
        normalized[(t["type"], *edge)] += 1
        if t["type"] == "token_transfer":
            receipt_transfers.append(edge)
    if Counter(receipt_transfers) != Counter(actual_transfers):
        raise ValueError("receipt token transfers differ from executed token calls")
    zero = "0x" + "00"*20
    expected_normalized = Counter(("token_transfer", *edge) for edge in actual_transfers)
    expected_normalized[("token_minting", WETH, zero, EXECUTOR, deposits)] += 1
    expected_normalized[("token_burning", WETH, EXECUTOR, zero, withdrawals)] += 1
    if normalized != expected_normalized:
        raise ValueError("normalized wrapping movements differ from native trace")
    collateral_delta = sum(amount*((to==EXECUTOR)-(source==EXECUTOR))
                           for token,source,to,amount in actual_transfers if token==addresses[1])
    if collateral_delta != 0:
        raise ValueError("collateral not fully converted")
    return {
        "status":"INDEXER_TRACE_ARITHMETIC_RECONCILED_NOT_FORK_REPRODUCED",
        "transaction_hash": TX, "block_hash": BLOCK_HASH, "tx_index": 1,
        "prior_transactions_unreplayed": 1, "trace_count": len(tree),
        "market_id":"0x"+market_id.hex(), "market_addresses":addresses,
        "borrower":"0x"+args[5].to_bytes(20,"big").hex(),
        "pre_accrual_market":asdict(pre_market), "borrow_rate_wad_per_second":rate,
        "accrual":asdict(accrued), "post_accrual_witness":asdict(witness),
        "quote":asdict(quote), "native_flows":native_flows,
        "executor_initial_weth_wei":initial_weth,
        "executor_final_weth_inferred_wei":initial_weth+residual,
        "executor_weth_increase_wei":residual,
        "executor_native_change_wei":native_delta,
        "coinbase_received_wei":coinbase_paid,
        "sender_gas_cost_wei":int(r["fee"]["value"]),
        "residual_minus_sender_gas_arithmetic_wei":residual-int(r["fee"]["value"]),
        "ledger": {
            "executor_weth": {"initial_observed":initial_weth,"wrapped_in":deposits,
                              "debt_out":quote.repaid_assets,"unwrap_out":withdrawals,
                              "final_inferred":initial_weth+residual},
            "executor_collateral": {"initial":None,"seized_in":quote.seized_assets,
                                    "converted_out":quote.seized_assets,"delta":collateral_delta,"final":None},
            "executor_native": {"initial":None,"conversion_in":deposits,"wrap_out":deposits,
                                "unwrap_in":withdrawals,"coinbase_out":coinbase_paid,"delta":native_delta,"final":None},
            "sender_gas_out_wei":int(r["fee"]["value"]),
            "dex_output_after_venue_costs_wei":deposits,
            "dex_fee_separately_verified_wei":None,"price_impact_separately_verified_wei":None,
            "builder_payment_attributed_wei":None,"proposer_payment_attributed_wei":None,
            "financing_outside_transaction":None,"consolidated_operator_final_assets":None,
        },
        "builder_income_wei":None, "nqc_realized_profit":None,
        "certified":False, "live_executable":False,
        "limitations":["Single indexer; no state-root proof or independent fork replay",
                       "Rate/oracle observed inside external winner; not an ex-ante NQC quote",
                       "Pre-existing WETH means this is not a zero-funded executor demonstration",
                       "Coinbase ownership and builder sponsorship unproved",
                       "Residual minus gas is arithmetic, not certified consolidated P&L"],
    }


def main() -> int:
    root = Path(__file__).parent / "evidence/2026-10-17"
    try:
        records = [json.loads((root/f"case_b{suffix}.json").read_text()) for suffix in ("_trace", "_block", "")]
        print(json.dumps(inspect(*records), indent=2))
        return 2
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(json.dumps({"status":"INVALID_TRACE", "reason":str(exc), "certified":False}))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
