"""Targeted First Gold provenance/absence check; reuses pinned NQC055 primitives."""
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
MANIFEST=json.loads((HERE/'SOURCE_MANIFEST.json').read_text())
pin=MANIFEST['files']['core']
module_path=REPO/pin['path']
if hashlib.sha256(module_path.read_bytes()).hexdigest()!=pin['sha256']:
    raise ValueError('NQC055 dependency changed')
spec=importlib.util.spec_from_file_location('nqc055_core_for056',module_path)
core=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=core
spec.loader.exec_module(core)
require=core.require

TX='0x34162fda07ca0ae1054d7c1252b8d1c48aba9a675fd3d09816393c29d8be50e4'
MARKET='0x0eed5a89c7d397d02fd0b9b8e42811ca67e50ed5aeaa4f22e506516c716cfbbf'
WETH='0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2'
PUF='0xd9a442856c234a39a81a089c06451ebaa4306a72'


def facts(row):
    require(type(row['chain']['id']) is int and row['chain']['id']==1,'wrong event chain')
    require(row['txHash']==TX and row['type']=='Liquidation','wrong event identity')
    market=row['market'];data=row['data']
    require(market['marketId']==MARKET,'wrong market')
    require(market['loanAsset']['address'].lower()==WETH and market['collateralAsset']['address'].lower()==PUF,'wrong assets')
    require(market['loanAsset']['decimals']==market['collateralAsset']['decimals']==18,'asset scale')
    return {'block':core.integer(row['blockNumber']),'tx_index':core.integer(row['txIndex']),
        'log_index':core.integer(row['logIndex']),'lltv':str(core.integer(market['lltv'])),
        'liquidator_claim':data['liquidator'].lower(),
        'repaid_WETH_raw':str(core.integer(data['repaidAssets'])),
        'seized_pufETH_raw':str(core.integer(data['seizedAssets'])),
        'repaid_shares_raw':str(core.integer(data['repaidShares'])),
        'bad_debt_assets_raw':str(core.integer(data['badDebtAssets']))}


def source_order(source):
    """Checks fixed-source call ordering, NOT compiled/runtime semantic verification."""
    segment=source[source.index('    function liquidate('):source.index('    function flashLoan(')]
    calls=['IERC20(marketParams.collateralToken).safeTransfer(msg.sender, seizedAssets);',
        'if (data.length > 0) IMorphoLiquidateCallback(msg.sender).onMorphoLiquidate(repaidAssets, data);',
        'IERC20(marketParams.loanToken).safeTransferFrom(msg.sender, address(this), repaidAssets);']
    offsets=[segment.index(call) for call in calls]
    require(offsets==sorted(offsets),'unexpected settlement order')
    return {'collateral_then_optional_callback_then_repayment':True,
        'verification_scope':'textual order in hash-pinned upstream source only',
        'candidate_used_callback':None,'candidate_runtime_bound_to_source':False,
        'source_statements':calls,'gas_sponsor_available':None,'sale_liquidity_available':None,
        'residue_after_all_obligations':None}


def review_corpus(corpus,review,s):
    seen={(h['containing_git_blob'],h['member'],h['sha256']) for h in corpus['identifier_hits']}
    signed_off={(r['blob'],r['member'],r['sha256']) for r in review}
    require(seen==signed_off and seen,'unreviewed or omitted corpus hits')
    require(not corpus['container_limits_or_errors'],'incomplete supported container scan')
    allowed={'SAME_PROVIDER_EVENT','NULL_RPC_RESPONSE','DERIVED_REPORT_OR_SELECTION','DOCUMENTATION_OR_TEST'}
    require(all(r['kind'] in allowed for r in review),'new primary evidence requires separate assessment')
    for name in ('forward','reverse','receipt'):
        require(any(h['containing_git_blob']==s.manifest['files'][name]['git_blob_sha1'] for h in corpus['identifier_hits']),
            'corpus omitted known positive control')
    return {'unique_blobs_scanned':corpus['unique_blobs'],
        'objects_and_archive_members_scanned':corpus['stats']['objects_or_members_scanned'],
        'matching_git_blobs':len({h['containing_git_blob'] for h in corpus['identifier_hits']}),
        'primary_target_header_body_receipt_or_trace_identified':False,
        'limitations':corpus['limitations']}


def analyze(s=None):
    s=s or core.Sources(MANIFEST);verified=s.verify_all()
    forward=s.json('forward');reverse=s.json('reverse')
    fp='/response/data/marketTransactions/items/91';rp='/response/data/marketTransactions/items/51'
    f=facts(forward['response']['data']['marketTransactions']['items'][91])
    r=facts(reverse['response']['data']['marketTransactions']['items'][51])
    require(f==r,'forward/reverse observation conflict')
    require((f['block'],f['tx_index'],f['log_index'])==(26104570,0,3),'unexpected reported position')
    require(forward['url']==reverse['url']=='https://api.morpho.org/graphql','event provider scope')
    receipt=s.json('receipt')
    require(receipt['request']['method']=='eth_getTransactionReceipt' and receipt['request']['params']==[TX],'receipt request identity')
    require(receipt['http_status']==200 and 'result' in receipt['response'] and receipt['response']['result'] is None,
            'receipt changed; new primary evidence needs analysis')
    earlier=s.json('earlier_candidates')['candidates'][2]
    lock=s.json('earlier_lock')
    require(earlier['tx_hash']==TX and earlier['classification']=='UNRATED_MISSING_WITNESS','earlier candidate identity')
    require(earlier['receipt_evidence']['gas_wei_per_transaction'] is None and earlier['net_profit'] is None,'earlier economic evidence changed')
    for name,filename in [('forward','page-000.json'),('reverse','reverse-000.json')]:
        require(lock['input_sha256'][filename]==s.manifest['files'][name]['sha256'],'selection lineage conflict')
    require(hashlib.sha256(s.raw('earlier_selector')).hexdigest()==lock['code_sha256'],'earlier selector provenance')
    previous=s.json('nqc055_summary')['proposed_next_probe']
    require(previous['tx_hash']==TX and previous['acquisition_authorized'] is False,'radar handoff identity')
    corpus=json.loads((HERE/'evidence/corpus.json').read_text())
    reviewed=json.loads((HERE/'HIT_REVIEW.json').read_text())['hits']
    inventory=review_corpus(corpus,reviewed,s)
    debt=int(f['repaid_WETH_raw']);collateral=int(f['seized_pufETH_raw'])
    require(debt==590976235877976338 and collateral==569144086683595914,'fixed candidate amounts')
    return {'schema':'nqc056-first-gold-v1','classification':'EVIDENCIA_INSUFICIENTE',
        'tx_hash':TX,'chain_id':1,'market_id':MARKET,'observations':f,
        'provenance':{'sources_verified':verified,'forward':s.ref('forward',fp),'reverse':s.ref('reverse',rp),
            'same_event_provider_count':1,'independent_positive_corroboration':False,
            'null_receipt':s.ref('receipt','/response/result'),
            'null_receipt_retrieved_at':receipt['retrieved_at_utc'],
            'earlier_selection':s.ref('earlier_candidates','/candidates/2'),
            'earlier_selection_locked_at':lock['locked_at_utc'],
            'earlier_selection_uses_identical_page_hashes':True,'rediscovery_is_new_opportunity':False},
        'corpus_review':inventory,
        'authentication':{'target_block_hash':None,'header':None,'transactions_root':None,'transaction_bytes':None,
            'membership_proof':None,'reported_index':0,'authenticated_index':None,
            'raw_receipt':None,'raw_trace':None,'event_emitter_authenticated':False,
            'market_oracle':None,'market_irm':None,'borrower':None,'executor_runtime':None,
            'if_index_zero_verified':'No preceding ordinary transactions. Parent state, fork/system transitions and target runtime/storage remain mandatory.',
            'historical_replay_attempted':False},
        'economics':{'observed_sale_output':None,'gross_surplus':None,'gas_used':None,'effective_gas_price':None,
            'inclusion_payment':None,'financing_premium':None,'other_obligations':None,
            'net_lower_bound':None,'net_upper_bound':None,'net_capturable_by_NQC':None,
            'necessary_sale_condition':{'scope':'Only if reported amounts equal actual received/repaid amounts and all collateral is sold, with nonnegative remaining obligations.',
                'output_asset':{'chain_id':1,'address':WETH,'decimals':18},
                'strict_positive_output_min_raw_before_other_costs':str(debt+1),
                'debt_cover_average_WETH_per_pufETH_fraction':str(Fraction(debt,collateral)),
                'observed_or_executable_price':None,'sufficient_for_net_profit':False},
            'no_scenario_economically_rejected':True},
        'financing_semantics':{**source_order(s.raw('morpho_source').decode()),
            'source':s.ref('morpho_source'),'upstream_commit':s.json('morpho_provenance')['upstream_commit']},
        'missing_minimum_packet':['canonical target header plus transaction bytes and authenticated membership/order',
            'complete receipt tied to target and receipt commitment, logs, gas used and effective gas price',
            'complete call trace or equivalent state/balance evidence for token/native transfers, sale route and inclusion payments',
            'liabilities outside trace, financing/gas-advance terms, ownership and competitive capture evidence'],
        'stop_reason':'No identified primary packet in frozen corpus; acquisition/retry not authorized. No replay or speculative optimization.',
        'triport_total_known':0,'triport_lifetime_budget':8,'new_RPC_requests':0,
        'safe_credential_channel_demonstrated':False,'unique_live_ledger_demonstrated':False,
        'commercial_admission':False}


if __name__=='__main__':
    print(json.dumps(analyze(),indent=2,sort_keys=True))
