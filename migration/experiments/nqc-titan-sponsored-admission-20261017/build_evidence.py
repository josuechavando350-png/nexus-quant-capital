"""Reconcile locked prior receipts plus three new runs; generate offline artifacts."""
import hashlib
import json
from pathlib import Path
from BUILDER_BALANCE_GATE import HERE, BASE, evm_layer, evaluate, frontier, group_cash
from run_identity import verify_base


def read(path): return json.loads(path.read_text())
def write(name, data): (HERE/name).write_text(json.dumps(data, indent=2, sort_keys=True)+'\n')
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def load(name):
    root = HERE if name.startswith('V') else BASE
    return read(root/'evidence'/f'{name}.json')
def local_gate(run, group, **kw):
    return evaluate(run, group, loss_cap_wei=10**18, founder_model_recourse_wei=0, **kw)


def main():
    verify_base(require_artifacts=False)
    old = read(BASE/'evidence/run-index.json')['runs']
    all_runs = {x['scenario']:load(x['scenario']) for x in old if x['scenario']!='A1_six_blocks'}
    all_runs.update({x['scenario']:load(x['scenario']) for x in read(HERE/'evidence/new-evm-index.json')['runs']})
    reconciled = {}; controls = {}
    for name,r in all_runs.items():
        # R003 controls use old RPC snapshots, not prestateTracer. Keep separate and explicitly reused.
        if not r.get('snapshot_source','').startswith('prestateTracer'):
            from reconcile_flows import reconcile
            l = reconcile(r); e={'classification':'PRIOR_RPC_SNAPSHOTS_RECONCILED','prefixes':[],'failures':[]}
        else:
            e = evm_layer(r); l = e.pop('ledger')
        controls[name] = {'EVM':e['classification'],'failures':e['failures'],
                          'sponsor_cash_delta_wei':l['sponsor']['cash_margin_wei'],
                          'U_received_wei':l['sponsor']['U_actually_returned_wei'],
                          'retained_advance_wei':l['nqc']['native_retained_advance_wei'],
                          'source_sha256':digest((HERE if name.startswith('V') else BASE)/'evidence'/f'{name}.json')}
        if name in ('A2_C1_zero_cash','A2_C1_high_gas') or name.startswith('V'):
            s=r['actors']['sponsor_and_topup_financier']; b=r['actors']['simulated_builder']
            reconciled[name]={'evidence_scope':'LOCAL_SYNTHETIC_ONLY', 'EVM':e,
                'cashflows_and_all_asset_balances':l,
                'distinct_address_cash_deltas_wei':{a:d['ETH'] for a,d in l['balance_delta_by_address'].items()},
                'explicit_group_hypothesis_addresses':sorted({s,b}),
                'group_cash_wei':group_cash(l,{s,b}),
                'group_after_1bp_wei':group_cash(l,{s,b})-l['sponsor']['opportunity_charge_1bp_wei'],
                'real_builder_recipient':None,'real_beneficial_ownership':None,
                'founder_max_recourse_wei':None}
    lo=all_runs['A2_C1_zero_cash']; hi=all_runs['A2_C1_high_gas']
    a=lo['actors']; b=a['simulated_builder']; s=a['sponsor_and_topup_financier']
    good=all_runs['V06_builder_funds_own_refund']; bad=all_runs['V05_builder_funds_external_refund']
    group={b,s}; single={b}
    variants={
      'V01_external_financier_2g':local_gate(lo,single),
      'V02_external_financier_21g':local_gate(hi,single),
      'V03_declared_same_owner_2g':local_gate(lo,group),
      'V04_declared_same_owner_21g':local_gate(hi,group),
      'V05_builder_funds_external_refund':local_gate(bad,single),
      'V06_builder_funds_own_refund':local_gate(good,single),
      'V07_partial_topup':local_gate(all_runs['V07_partial_topup'],single),
      'V08_proposer_ownership_not_authenticated':local_gate(lo,group|{a['proposer']}),
      'V09_provider_value_distinction':{p:local_gate(good,single,provider=p,extra_sponsored_value_wei=1) for p in ('Titan','Quasar')},
      'V10_real_identity_and_terms_unknown':evaluate(good,single,scope='UNVERIFIED_EXTERNAL'),
      'V11_required_steps_declared_optional':{
          'revert_allowed':local_gate(good,single,reverting_labels=['liquidate']),
          'drop_allowed':local_gate(good,single,dropping_labels=['return_unused_advance'])},
      'V12_joint_prefix_and_cost_frontier':frontier(good),
    }
    # Economic ownership cannot erase a network fee from the retained internal payment.
    assert reconciled['A2_C1_zero_cash']['group_cash_wei']==45321588000000000
    assert reconciled['A2_C1_high_gas']['group_cash_wei']==876674000000000
    assert reconciled['A2_C1_high_gas']['cashflows_and_all_asset_balances']['sponsor']['cash_margin_wei']==-1123326000000000
    assert reconciled['V06_builder_funds_own_refund']['group_cash_wei']==45363588000000000
    assert variants['V05_builder_funds_external_refund']['classification']=='REFUTED'
    assert variants['V06_builder_funds_own_refund']['classification']=='PASS_LOCAL'
    assert variants['V10_real_identity_and_terms_unknown']['classification']=='UNKNOWN'
    write('IDENTITY_AND_CASHFLOW_LEDGER.json',{
        'classification':'MODEL_ONLY','wei_integers':True,'ETH_and_WETH_never_aggregated':True,
        'external_formula':'R + U + V - A - F - P - O',
        'group_formula':'sum(actual external inflows) - sum(actual external outflows); internal amounts cancel, gas remains',
        'scenarios':reconciled,'founder_max_recourse_wei':None,'realized_NQC_PnL_USD':0})
    write('evidence/gate-results.json',{'variant_limit':12,'new_EVM_variants':3,'variants':variants,
                                      'reused_controls':controls})
    intent={
      'kind':'OFFLINE_UNSIGNED_INTENT_NOT_ETH_SENDBUNDLE_REQUEST','chain_id':31337,
      'actual_builder_acceptance':'NOT_TESTED','production_txs':None,
      'no_signed_transaction_bytes':True,'original_code_commit':'9988e425bdd8e5e9a9db7666cd9e8122404c39e0',
      'historical_case_B':'BLOCKED_PRESTATE','models':{},
      'provider_projection':{
          'real_builder_beneficiary':None,'real_builder_funding_account':None,
          'real_builder_funding_nonce':None,'target_blockNumber':None,
          'minTimestamp':None,'maxTimestamp':{'Titan':'NOT_DOCUMENTED_IN_REVIEWED_SCHEMA','Quasar':None},
          'revertingTxHashes':[],'droppingTxHashes':[],
          'refundPercent':'UNSET','refundRecipient':'UNSET','replacementUuid':None,
          'replacementSeqNumber':None,
          'builder_inserted_topup':'PLACEHOLDER: generated by builder, not a user-signed transaction',
          'return_U':'Depends on actual advance, price, recipient and inclusion. None authenticated for real provider.',
          'CREATE_coverage_and_failure_terms':None}}
    for label,r in [('I_external_financier_distinct',lo),('II_builder_is_financier',good)]:
        source=(BASE if label.startswith('I_') else HERE)/'evidence'/f'{r["scenario"]}.json'
        txs=[]
        for i,t in enumerate(r['transactions']):
            req=t['request']; txs.append({'label':t['label'],'dependency_labels':[x['label'] for x in r['transactions'][:i]],
                'unsigned_local_request':req,'data_sha256':hashlib.sha256(bytes.fromhex(req['data'][2:])).hexdigest(),
                'predicted_CREATE_address':t['receipt']['contractAddress'],
                'origin':'LAB_FINANCIER_PLACEHOLDER' if t['label']=='topup' else 'LOCAL_UNSIGNED',
                'receipt_pointer':f'../{source.parent.parent.name}/evidence/{source.name}#/transactions/{i}'})
        roles=r['actors']; owners={addr:('builder' if addr==roles['simulated_builder'] else name)
                                  for name,addr in roles.items()}
        if label.startswith('II_'): owners[roles['simulated_builder']]='builder_and_financier'
        intent['models'][label]={'scope':'LAB_ASSIGNED_OWNERSHIP_NOT_REAL_IDENTITIES',
            'actors':roles,'declared_beneficial_owners':owners,'initial_state':r['initial'],
            'initial_NQC_nonce':0,'initial_executor_code':'0x','transactions':txs,
            'bytecodes_and_constructors':'Full creation data above; pinned original artifacts in SOURCE_LOCK.json of 004',
            'repayment_asset':'WETH','repayment_base_units':8*10**18,
            'contract_refund_native_wei':5*10**16,'proposer_tip_native_wei':4*10**16,
            'source_sha256':digest(source),'founder_max_recourse_wei':None,
            'separate_builder_fee_wei':2*10**15 if label.startswith('I_') else 0}
    write('C1_BUNDLE_INTENT.json',intent)
    write('evidence/frontier.json',variants['V12_joint_prefix_and_cost_frontier'])
    print(json.dumps({'new_variants':3,'offline_variant_groups':len(variants),
                     'prior_scenarios_reconciled':len(all_runs)-3,
                     'frontier':variants['V12_joint_prefix_and_cost_frontier']}))

if __name__=='__main__': main()
