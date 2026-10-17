"""Generate deterministic offline vectors for independent Solidity parity tests."""
import argparse
import hashlib
import json
import random
from pathlib import Path
from bundler3_abi import Call, abi_encode_calls, adapter_flashloan_calldata, flashloan_callback_hash
from morpho_liquidation_math import PostAccrualWitness, calculate, to_assets
from morpho_interest_math import taylor_compounded


def word(n): return n.to_bytes(32,"big")
def static_array(rows): return word(32)+word(len(rows))+b"".join(word(n) for row in rows for n in row)


def products():
    rng = random.Random(0x4E5143)
    rows = []
    for _ in range(64):
        assets = rng.randrange(10**6, 10**24)
        shares = assets*10**6 + rng.randrange(1,10**6)
        borrower = shares//10
        price = rng.randrange(10**30, 10**38)
        debt = to_assets(borrower, assets, shares, up=True)
        collateral = debt*10**36//price
        w = PostAccrualWitness(assets,shares,borrower,collateral,price,rng.randrange(1,10**18))
        q = calculate(w, borrower//2)
        rows.append([*vars(w).values(),q.repaid_shares,q.seized_assets,q.repaid_assets,
                     q.liquidation_incentive_factor,q.borrower_debt_assets_rounded_up,q.max_safe_borrow_assets])
    historical = PostAccrualWitness(26043463345322388797,23705175968761821157206366,
                  23704155994056782756952445,25338307877058627798,1087603514108019748000000000000000000,
                  945000000000000000)
    q = calculate(historical,23701785578457377078676750)
    rows.append([*vars(historical).values(),q.repaid_shares,q.seized_assets,q.repaid_assets,
                 q.liquidation_incentive_factor,q.borrower_debt_assets_rounded_up,q.max_safe_borrow_assets])
    interest=[]
    for _ in range(64):
        rate=rng.randrange(0,10**12);elapsed=rng.randrange(0,10**7);assets=rng.randrange(1,10**25)
        factor=taylor_compounded(rate,elapsed)
        interest.append([rate,elapsed,assets,factor,assets*factor//10**18])
    interest.append([3559581937,913008,25958961383310086496,
                     taylor_compounded(3559581937,913008),84501962012302301])
    a="0x"+"11"*20;b="0x"+"22"*20
    calls=(Call(a,b"\x01"*33,7,False,b"\xab"*32),Call(b,b"",0),Call(a,bytes(range(31)),2))
    return {"math_parity.hex":static_array(rows),"interest_parity.hex":static_array(interest),
            "calls_parity.hex":abi_encode_calls(calls),
            "callback_hash_parity.hex":flashloan_callback_hash(calls),
            "flashloan_abi_parity.hex":adapter_flashloan_calldata(b,1234567,calls)}


def main():
    p=argparse.ArgumentParser();p.add_argument("--check",action="store_true");args=p.parse_args()
    folder=Path(__file__).parent/"fixtures"
    for filename,content in products().items():
        data="0x"+content.hex()
        path=folder/filename
        if args.check:
            if path.read_text()!=data: raise ValueError(f"stale fixture: {filename}")
        else: path.write_text(data)
    print("5 parity fixtures verified" if args.check else "5 parity fixtures generated")


if __name__=="__main__":main()
