"""Local selection rejection: restore trial state, include an empty block, prove no loss.

Snapshot restoration is an experimental simulation boundary, not an ability to cancel mined txs.
"""
import argparse
import json
from local_node import HERE, node, save
from run_coordinated import run_case, state
from economics import evaluate

def main():
    p=argparse.ArgumentParser();p.add_argument('--anvil',required=True);args=p.parse_args()
    art=json.loads((HERE/'build/artifacts.json').read_text());results=[]
    with node(args.anvil,art,pool_override=True) as lab:
        lab.setup()
        for name,kw in [('reject_C2_cash0',{'architecture':'C2'}),('reject_financier_loss',{'high':True})]:
            checkpoint=lab.rpc('evm_snapshot'); before=state(lab)
            nonces={a:lab.rpc('eth_getTransactionCount',[a,'latest']) for a in lab.actors.values()}
            trial=run_case(lab,'POLICY_trial_'+name,**kw) # run_case always restores the candidate snapshot.
            policy=evaluate(trial)['policy'];assert not policy['admitted_under_measured_and_explicit_lab_costs']
            lab.rpc('anvil_dropAllTransactions');lab.rpc('evm_setAutomine',[False]);lab.rpc('evm_mine')
            after=state(lab);block=lab.rpc('eth_getBlockByNumber',['latest',False])
            assert block['transactions']==[]
            for key in ('balances','position','reserves','market_totals','oracle'):
                assert before[key]==after[key]
            assert all(lab.rpc('eth_getTransactionCount',[a,'latest'])==n for a,n in nonces.items())
            results.append({'name':name,'classification':'EVM_LOCAL_PASS_SELECTION_CONTROL',
                'policy':policy,'selected_block':block,'before':before,'after':after,
                'actual_selected_transaction_count':0,'actual_selected_gas_cost_wei':0,
                'discarded_local_trial':f'POLICY_trial_{name}.json',
                'no_real_builder_policy_or_rollback_guarantee':True})
            assert lab.rpc('evm_revert',[checkpoint])
    save('policy-exclusion',results)
    print(json.dumps({'selection_controls':len(results),'included_financial_transactions':0,'local_nodes_stopped':True}))

if __name__=='__main__':main()
