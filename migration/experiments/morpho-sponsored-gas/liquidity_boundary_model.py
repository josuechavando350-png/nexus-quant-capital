"""Exact synthetic Uniswap V2 economics, checked against saved original-code EVM traces."""
import gzip
import json
import re
from pathlib import Path
from morpho_liquidation_math import PostAccrualWitness, calculate

WAD=10**18
DEBT=8*WAD
NATIVE_BUDGET=WAD//10
MINIMUM_PROFIT=WAD//100


def seized_collateral() -> int:
    witness=PostAccrualWitness(100*WAD,100*WAD*10**6,8*WAD*10**6,10*WAD,9*10**35,86*10**16)
    return calculate(witness,8*WAD*10**6).seized_assets


def quote(reserve: int) -> dict:
    if type(reserve) is not int or not 0<reserve<2**112:
        raise ValueError('positive uint112 reserve required')
    amount=seized_collateral();loan_reserve=reserve*9//10
    out=amount*997*loan_reserve//(reserve*1000+amount*997)
    no_fee=amount*loan_reserve//(reserve+amount)
    spot=amount*loan_reserve//reserve
    return {'collateral_in':amount,'collateral_reserve':reserve,'loan_reserve':loan_reserve,
            'spot_value_units':spot,'price_impact_without_fee_units':spot-no_fee,
            'fee_effect_on_output_units':no_fee-out,'executable_out_units':out,
            'repayment_units':DEBT,'native_budget_wei':NATIVE_BUDGET,
            'operator_weth_if_settled':out-DEBT-NATIVE_BUDGET,
            'local_output_bound_satisfied':out>=DEBT+NATIVE_BUDGET+MINIMUM_PROFIT}


def reconcile_trace(text: str) -> list[dict]:
    rows=[]
    for line in text.splitlines():
        if 'emit Scenario(' not in line: continue
        line=re.sub(r' \[[^]]*\]','',line)
        m=re.search(r'Scenario\(flashRoute: (true|false), morphoCash: (\d+), collateralReserve: (\d+), dexOut: (\d+), success: (true|false), operatorWeth: (\d+)\)',line)
        if not m:raise ValueError('unrecognized scenario trace')
        flash,cash,reserve,out,success,profit=m.groups()
        cash,reserve,out,profit=map(int,(cash,reserve,out,profit))
        q=quote(reserve);expected=q['local_output_bound_satisfied'] and (flash=='false' or cash>=DEBT)
        if out!=q['executable_out_units'] or (success=='true')!=expected or profit!=(q['operator_weth_if_settled'] if expected else 0):
            raise ValueError('EVM/model discrepancy')
        rows.append({'flash_route':flash=='true','morpho_cash_units':cash,'pool_collateral_units':reserve,
                     'dex_out_units':out,'settled':success=='true','operator_weth_units':profit})
    if len(rows)!=21:raise ValueError('missing or extra scenario traces')
    expected={(f,c,1000*WAD) for f in (False,True) for c in (0,1,DEBT-1,DEBT,92*WAD)}
    expected|={(f,DEBT,r*WAD) for f in (False,True) for r in (20,100,1000,10000)}
    if {(r['flash_route'],r['morpho_cash_units'],r['pool_collateral_units']) for r in rows}!=expected:
        raise ValueError('scenario coverage changed')
    return rows


def main() -> int:
    folder=Path(__file__).parent/'evidence/2026-10-17-continuation'
    text=gzip.decompress((folder/'liquidity-boundary-traces.log.gz').read_bytes()).decode()
    rows=reconcile_trace(text)
    result={'status':'LOCAL_ORIGINAL_CODE_SYNTHETIC_STATE','evm_model_rows_matched':len(rows),'scenarios':rows,
            'depth_economics':[quote(r*WAD) for r in (20,100,1000,10000)],
            'owner_initial_eth_units':0,'owner_initial_weth_units':0,
            'native_allocations_wei':{'synthetic_sponsor':5*10**16,'coinbase':4*10**16,'operator':10**16},
            'actual_gas_cost_wei':None,'verified_sponsor_receipts':False,
            'historical_replay':False,'capture_probability':None,'certified':False,
            'limitations':['Synthetic LP liquidity and mock assets/oracle; original protocol/pair code',
                           'Function gas excludes transaction admission and is not production cost',
                           'Payments to test addresses do not verify builder identities or advances',
                           'No economically admitted historical operation']}
    print(json.dumps(result,indent=2));return 2


if __name__=='__main__':raise SystemExit(main())
