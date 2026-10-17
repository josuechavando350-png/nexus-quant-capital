"""Same-block candidate simulation, with independent per-index state diffs and receipts.

No transaction-level rollback across the package is claimed. All identities/state are synthetic.
"""
import argparse
import copy
import json
import sys
from pathlib import Path
from local_node import HERE, node, ref, save

sys.path.insert(0, str(HERE.parent / 'morpho-sponsored-gas'))
from bundler3_abi import Call, encode_flashloan_top_call, multicall_calldata

E = ref.E
SEIZED = 9278589654372535368
OUT = 8249365645570551238

def created(sender, nonce):
    # RLP CREATE address; nonces used by this finite harness are below 128.
    assert 0 <= nonce < 128
    rlp = b'\x94' + bytes.fromhex(sender[2:]) + (b'\x80' if nonce == 0 else bytes([nonce]))
    return '0x' + ref.kh(bytes([0xc0 + len(rlp)]) + rlp)[-20:].hex()

def state(lab):
    s = lab.state()
    s.update(market=lab.market, market_id=lab.market_id,
             market_totals=ref.ints(lab.call(lab.actors['Morpho'], 'market(bytes32)', [lab.market_id])),
             oracle=ref.ints(lab.call(lab.actors['LabOracle'], 'price()'))[0],
             parent=lab.rpc('eth_getBlockByNumber', ['latest', False]))
    return s

def set_cash(lab, cash):
    if not cash:
        return
    a = lab.actors; other = a['other_borrower']
    # Return real previously-borrowed fixture WETH through original Morpho.repay.
    lab.send('cash_approval', other, a['WETH'], 'approve(address,uint256)', [a['Morpho'], cash])
    lab.send('cash_repayment', other, a['Morpho'], f'repay({ref.MARKET},uint256,uint256,address,bytes)',
             lab.market + [cash, 0, other, b''])
    assert lab.token(a['WETH'], a['Morpho']) == cash

def build_package(lab, architecture='C1', mode='success', advance=3*10**16, base_fee=10**9):
    a = lab.actors; op = a['nqc_sender_and_beneficiary']; sponsor = a['sponsor_and_topup_financier']
    nonce = {who: int(lab.rpc('eth_getTransactionCount', [who, 'latest']), 16) for who in (op, sponsor)}
    requests = []; cap = 3*10**9 if base_fee == 10**9 else 30*10**9
    def add(label, sender, to=None, data='0x', value=0, gas=2500000, actor=None):
        n = nonce[sender]; nonce[sender] += 1
        tx = {'from': sender, 'data': data, 'value': hex(value), 'gas': hex(gas), 'nonce': hex(n),
              'maxFeePerGas': hex(cap), 'maxPriorityFeePerGas': hex(10**9)}
        if to:
            tx['to'] = to
        elif actor:
            a[actor] = created(sender, n)
        requests.append({'label': label, 'request': tx})
        return a.get(actor)
    def deploy(name, args=(), actor=None, gas=4000000):
        if mode == 'predeployed':
            return a[actor or name]
        return add(actor or name, op, data=lab.art[name]['bytecode'] + ref.encode(args).hex(),
                   gas=gas, actor=actor or name)
    add('topup', sponsor, op, value=advance, gas=21000)
    if mode == 'topup_only':
        return requests
    bridge = deploy('LabV2Adapter', [a['dex_pair'], a['ERC20'], a['WETH']], 'nqc_adapter')
    if architecture == 'C1':
        ex = deploy('NqcMorphoSponsoredLiquidation',
                     [ref.ZERO if mode == 'bad_create' else op, a['Morpho'], bridge, a['WETH']], 'nqc_executor')
        lab.settlement_contract = ex
        changes = {}
        if mode == 'slippage': changes['min_out'] = OUT + 1
        if mode == 'expired': changes['expiry'] = 0
        if mode == 'refund_reject': changes['sponsor'] = a['RejectNative']
        if mode == 'low_tip': changes['tip'] = 4*10**16-1
        data = ref.calldata(f'execute({ref.PLAN},bytes,bytes)', lab.plan(changes))
        if mode not in ('deploy_only', 'bad_create'):
            add('liquidate', op, ex, data)
    else:
        bundler = deploy('Bundler3')
        metadata = deploy('ConstructorMetadataFixture', [a['WETH']])
        general = deploy('EthereumGeneralAdapter1',
                    [bundler, a['Morpho'], a['WETH'], metadata, a['ERC20'], metadata], gas=8000000)
        lab.settlement_contract = general
        def call(to, sig, args):
            return Call(to, bytes.fromhex(ref.calldata(sig, args)[2:]))
        nested = (
            call(general, 'erc20Transfer(address,address,uint256)', [a['WETH'], bundler, 8*E]),
            call(a['WETH'], 'approve(address,uint256)', [a['Morpho'], 8*E]),
            call(a['Morpho'], f'liquidate({ref.MARKET},address,uint256,uint256,bytes)',
                 lab.market + [a['borrower'], 0, lab.shares, b'']),
            call(a['WETH'], 'approve(address,uint256)', [a['Morpho'], 0]),
            call(a['ERC20'], 'approve(address,uint256)', [bridge, SEIZED]),
            call(bridge, 'swapExactInput(address,address,uint256,uint256,bytes)',
                 [a['ERC20'], a['WETH'], SEIZED, 811*10**16, b'']),
            call(a['ERC20'], 'approve(address,uint256)', [bridge, 0]),
            call(a['WETH'], 'transfer(address,uint256)', [general, 8*E+9*10**16]),
            call(general, 'unwrapNative(uint256,address)', [5*10**16, sponsor]),
            call(general, 'unwrapNative(uint256,address)', [4*10**16, lab.coinbase]),
            call(a['WETH'], 'transfer(address,uint256)', [op, OUT-8*E-9*10**16]),
        )
        data = '0x' + multicall_calldata((encode_flashloan_top_call(general, a['WETH'], 8*E, nested),)).hex()
        add('liquidate', op, bundler, data)
    if mode not in ('deploy_only', 'bad_create', 'omit_return'):
        add('return_unused_advance', op, a['RejectNative'] if mode == 'return_reject' else sponsor,
            gas=40000 if mode == 'return_reject' else 21000)
        requests[-1]['request']['maxFeePerGas'] = hex(base_fee + 10**9)
    if mode not in ('deploy_only', 'bad_create'):
        add('separate_builder_fee', sponsor, a['simulated_builder'], value=2*10**15, gas=21000)
    if mode == 'omit_deploy':
        # Valid consecutive nonces, but call has no deployed recipient code.
        requests = [t for t in requests if t['label'] not in ('nqc_adapter', 'nqc_executor')]
        n = 0
        for t in requests:
            if t['request']['from'] == op:
                t['request']['nonce'] = hex(n); n += 1
    if mode == 'wrong_nonce':
        requests[2]['request']['nonce'] = '0x0'  # Duplicates first CREATE, same fees: pool must reject.
    if mode == 'priority_change':
        requests[-1]['request']['maxPriorityFeePerGas'] = hex(2*10**9)
    return requests

def diff_balances(before, state_diff, actors):
    """Decode balances independently from EVM prestateTracer, not Transfer/call flows.

    Pinned Solmate ERC20.balanceOf slot 3; V2 ERC20.balanceOf slot 1.
    Empty post entries in geth-style diffMode mean deletion/zero.
    """
    after = copy.deepcopy(before)
    pre = state_diff['pre']; post = state_diff['post']
    for who, balances in before.items():
        p = pre.get(who, {}); q = post.get(who, {})
        if 'balance' in p or 'balance' in q:
            assert balances['ETH'] == int(p.get('balance', '0x0'), 16), ('native prestate', who)
            after[who]['ETH'] = int(q.get('balance', '0x0'), 16)
        for token, asset, slot in ((actors['WETH'], 'WETH', 3), (actors['ERC20'], 'COLLATERAL', 1)):
            key = '0x' + ref.kh(ref.word(who) + ref.word(slot)).hex()
            pstore = pre.get(token, {}).get('storage', {}); qstore = post.get(token, {}).get('storage', {})
            if key in pstore or key in qstore:
                assert balances[asset] == int(pstore.get(key, '0x0'), 16), ('token prestate', who, asset)
                after[who][asset] = int(qstore.get(key, '0x0'), 16)
    return after

def execute_block(lab, requests, base_fee, name, observe=True):
    # EVM snapshot rollback is not a guarantee that candidate-pool entries are cleared.
    # Isolate each finite candidate explicitly; this is NOT a production cancellation API.
    lab.rpc('anvil_dropAllTransactions')
    assert lab.rpc('txpool_status') == {'pending': '0x0', 'queued': '0x0'}
    initial = state(lab); before = initial['balances']; records = []; rejections = []; pending = []
    lab.rpc('evm_setAutomine', [False])
    lab.rpc('anvil_setNextBlockBaseFeePerGas', [hex(base_fee)])
    timestamp = int(initial['parent']['timestamp'], 16) + 1
    lab.rpc('evm_setNextBlockTimestamp', [timestamp])
    for item in requests:
        try:
            h = lab.rpc('eth_sendUnsignedTransaction', [item['request']])
            pending.append((item, h))
        except ref.RPCError as exc:
            rejections.append({**item, 'error': str(exc), 'receipt': None})
    assert all(lab.rpc('eth_getTransactionReceipt', [h]) is None for _, h in pending)
    lab.rpc('evm_mine')
    included = []; not_included = []
    for item, h in pending:
        receipt = lab.rpc('eth_getTransactionReceipt', [h])
        if receipt is None:
            not_included.append({**item, 'hash': h, 'reason': 'not mined in candidate block'})
        else:
            included.append((item, receipt))
    included.sort(key=lambda pair: int(pair[1]['transactionIndex'], 16))
    for item, receipt in included:
        if not observe:
            records.append({**item, 'receipt': receipt,
                            'gas_cost_wei': int(receipt['gasUsed'], 16)*int(receipt['effectiveGasPrice'], 16)})
            continue
        h = receipt['transactionHash']
        trace = lab.rpc('debug_traceTransaction', [h, {'tracer': 'callTracer'}])
        diff = lab.rpc('debug_traceTransaction', [h, {'tracer': 'prestateTracer', 'tracerConfig': {'diffMode': True}}])
        after = diff_balances(before, diff, lab.actors)
        block = lab.rpc('eth_getBlockByHash', [receipt['blockHash'], False])
        records.append({**item, 'receipt': receipt, 'trace': trace, 'state_diff': diff,
                        'block': {k: block[k] for k in ('hash', 'parentHash', 'number', 'timestamp', 'baseFeePerGas', 'miner')},
                        'before': before, 'after': after,
                        'gas_cost_wei': int(receipt['gasUsed'], 16)*int(receipt['effectiveGasPrice'], 16)})
        before = after
    final = state(lab)
    if observe:
        assert before == final['balances'], 'per-index state diffs disagree with actual end-block balanceOf/getBalance'
    liquidation_completed = final['position'][1] == 0
    return_received = any(t['label']=='return_unused_advance' and int(t['receipt']['status'],16)==1
                          and t['request'].get('to')==lab.actors['sponsor_and_topup_financier']
                          and int(t['request']['value'],16)>0 for t in records)
    complete_package = (liquidation_completed and return_received and not not_included and not rejections
                        and all(int(t['receipt']['status'],16)==1 for t in records))
    return {'scenario': name, 'chain_id': 31337, 'actors': dict(lab.actors),
            'settlement_contract': getattr(lab, 'settlement_contract', None),
            'initial': initial, 'final': final, 'transactions': records,
            'rpc_rejections': rejections, 'accepted_not_included': not_included,
            'node_command': lab.command, 'snapshot_source': 'prestateTracer independent storage/native diff; end-block RPC cross-check',
            'flags': {'EVM_LOCAL_PASS': complete_package, 'LIQUIDATION_COMPLETED': liquidation_completed,
                      'HISTORICAL_STATE_VERIFIED': None, 'BUILDER_REAL_ACCEPTED': None,
                      'NO_RECOURSE_FINANCING_VERIFIED': None, 'COMPETITIVE_CAPTURE_VERIFIED': None}}

def run_case(lab, name, architecture='C1', mode='success', cash=0, high=False, advance=None):
    outer = lab.rpc('evm_snapshot'); actors = dict(lab.actors)
    lab.records = []; lab.rejections = []
    lab.rpc('evm_setAutomine', [True])
    lab.coinbase = actors['proposer']; lab.rpc('anvil_setCoinbase', [lab.coinbase])
    set_cash(lab, cash)
    if mode == 'healthy':
        lab.send('healthy_precondition', actors['setup'], actors['LabOracle'], 'setPrice(uint256)', [2*10**36])
    if mode == 'proposer_reject':
        lab.coinbase = actors['RejectNative']; lab.rpc('anvil_setCoinbase', [lab.coinbase])
    if mode == 'predeployed':
        s = actors['setup']; a = lab.actors
        lab.deploy('LabV2Adapter', s, [a['dex_pair'], a['ERC20'], a['WETH']], label='nqc_adapter')
        lab.deploy('Bundler3', s)
        metadata = lab.deploy('ConstructorMetadataFixture', s, [a['WETH']])
        lab.deploy('EthereumGeneralAdapter1', s, [a['Bundler3'], a['Morpho'], a['WETH'], metadata, a['ERC20'], metadata])
    preparation = lab.records; lab.records = []
    base_fee = (20 if high else 1)*10**9
    advance = advance if advance is not None else (3*10**17 if high else 3*10**16)
    requests = build_package(lab, architecture, mode, advance, base_fee)
    if mode == 'fee_discrepancy':
        # Valid caps, but quote assumed 2 gwei while actual price will be 3 gwei.
        base_fee = 2*10**9
        for t in requests: t['request']['maxFeePerGas'] = hex(4*10**9)
    checkpoint = lab.rpc('evm_snapshot')
    trial = execute_block(lab, requests, base_fee, name + '_planning', observe=False)
    actual_cost = sum(t['gas_cost_wei'] for t in trial['transactions']
                      if t['request']['from'] == actors['nqc_sender_and_beneficiary'])
    assert lab.rpc('evm_revert', [checkpoint])
    # This is a bounded local pre-simulation, NOT a builder's promise of price/inclusion.
    for item in requests:
        if item['label'] == 'return_unused_advance':
            item['request']['value'] = hex(advance - actual_cost)
            if mode == 'return_reject':
                trial_return = next(t for t in trial['transactions'] if t['label'] == 'return_unused_advance')
                other_cost = actual_cost - trial_return['gas_cost_wei']
                # Reserve the full maximum upfront cost so the attempted U is actually mined/reverted.
                item['request']['value'] = hex(advance-other_cost-int(item['request']['gas'],16)*int(item['request']['maxFeePerGas'],16))
    result = execute_block(lab, requests, base_fee, name)
    result.update(architecture=architecture, mode=mode, fixture_cash_wei=cash,
                  preparation_transactions=preparation,
                  planning={'method': 'one local candidate block simulated then snapshot restored',
                            'discarded_receipts_not_counted': True, 'expected_operator_gas_cost_wei': actual_cost,
                            'actual_base_fee_wei': base_fee, 'advance_wei': advance})
    expected_failure = mode in ('healthy', 'slippage', 'expired', 'refund_reject', 'proposer_reject',
                               'bad_create', 'topup_only', 'deploy_only', 'wrong_nonce', 'omit_deploy') or (architecture == 'C2' and cash < 8*E)
    assert result['flags']['LIQUIDATION_COMPLETED'] == (not expected_failure), (name, 'unexpected liquidation outcome')
    if not expected_failure:
        assert result['final']['balances'][actors['Morpho']]['WETH'] == cash+8*E
        assert result['final']['balances'][actors['nqc_sender_and_beneficiary']]['WETH'] == OUT-8*E-9*10**16
    else:
        assert result['initial']['position'] == result['final']['position']
        assert result['initial']['reserves'] == result['final']['reserves']
    if architecture == 'C2':
        a = lab.actors
        result['post_call_authorizations'] = {
            'bundler_morpho_allowance': ref.ints(lab.call(a['WETH'], 'allowance(address,address)', [a['Bundler3'], a['Morpho']]))[0],
            'bundler_bridge_allowance': ref.ints(lab.call(a['ERC20'], 'allowance(address,address)', [a['Bundler3'], a['nqc_adapter']]))[0],
            'general_morpho_allowance': ref.ints(lab.call(a['WETH'], 'allowance(address,address)', [a['EthereumGeneralAdapter1'], a['Morpho']]))[0],
            'initiator': lab.call(a['Bundler3'], 'initiator()'), 'reenter_hash': lab.call(a['Bundler3'], 'reenterHash()')}
        assert result['post_call_authorizations']['bundler_morpho_allowance'] == 0
        assert result['post_call_authorizations']['bundler_bridge_allowance'] == 0
        assert int(result['post_call_authorizations']['initiator'], 16) == 0
        assert int(result['post_call_authorizations']['reenter_hash'], 16) == 0
        for who in ('nqc_adapter', 'Bundler3', 'EthereumGeneralAdapter1'):
            assert all(v == 0 for v in result['final']['balances'][a[who]].values())
    save(name, result)
    assert lab.rpc('evm_revert', [outer]); lab.actors = actors
    return result

def main():
    p = argparse.ArgumentParser(); p.add_argument('--anvil', required=True); p.add_argument('--only')
    args = p.parse_args(); artifacts = json.loads((HERE / 'build/artifacts.json').read_text()); index = []
    (HERE / 'evidence/run-index.json').unlink(missing_ok=True)
    with node(args.anvil, artifacts, pool_override=True) as lab:
        lab.setup()
        save('setup', {'report': lab.setup_report, 'transactions': lab.setup_records})
        # Reproduce the exact six-block reference, preserving original files.
        checkpoint = lab.rpc('evm_snapshot'); actors = dict(lab.actors)
        baseline = lab.scenario('A1_six_blocks')
        assert sum(int(t['receipt']['gasUsed'], 16) for t in baseline['transactions']) == 2339206
        baseline['settlement_contract'] = baseline['actors']['nqc_executor']
        baseline['architecture'] = 'C1'; save('A1_six_blocks', baseline)
        index.append({'scenario': 'A1_six_blocks', 'status': 'EVM_LOCAL_PASS'})
        assert lab.rpc('evm_revert', [checkpoint]); lab.actors = actors
        cases = [
            ('A2_C1_zero_cash', {}), ('A2_C1_cash8', {'cash': 8*E}),
            ('C2a_cash8', {'architecture': 'C2', 'cash': 8*E}),
            ('C2b_cash0', {'architecture': 'C2'}),
            ('C2b_cash_below', {'architecture': 'C2', 'cash': 8*E-1}),
            ('C2_hypothetical_predeployed', {'architecture': 'C2', 'cash': 8*E, 'mode': 'predeployed'}),
            ('A2_C1_high_gas', {'high': True}),
            ('A3_topup_only', {'mode': 'topup_only'}), ('A3_deploy_only', {'mode': 'deploy_only'}),
            ('A3_bad_create', {'mode': 'bad_create'}), ('A3_healthy', {'mode': 'healthy'}),
            ('A3_slippage_one_wei', {'mode': 'slippage'}), ('A3_refund_reject', {'mode': 'refund_reject'}),
            ('A3_proposer_reject', {'mode': 'proposer_reject'}), ('A3_expired', {'mode': 'expired'}),
            ('A3_wrong_nonce', {'mode': 'wrong_nonce'}), ('A3_return_reject', {'mode': 'return_reject'}),
            ('A3_omit_return', {'mode': 'omit_return'}),
            ('A3_excess_no_return', {'mode': 'omit_return', 'advance': 3*10**17}),
            ('A3_excess_returned', {'advance': 3*10**17}),
            ('A3_low_tip', {'mode': 'low_tip'}), ('A3_omit_deploy', {'mode': 'omit_deploy'}),
            ('A3_fee_discrepancy', {'mode': 'fee_discrepancy'}),
        ]
        for name, kw in cases:
            if args.only and name != args.only: continue
            result = run_case(lab, name, **kw)
            item = {'scenario': name, 'status': 'EVM_LOCAL_PASS' if result['flags']['EVM_LOCAL_PASS'] else 'EXPECTED_NEGATIVE_CONTROL',
                    'included': len(result['transactions']), 'gas': sum(int(t['receipt']['gasUsed'],16) for t in result['transactions'])}
            index.append(item); print(json.dumps(item), flush=True)
        if not args.only:
            for name, mode in [('R003_one_wei_underpay','underpay_control'), ('R003_dust','dust')]:
                checkpoint = lab.rpc('evm_snapshot'); actors = dict(lab.actors)
                lab.rpc('evm_setAutomine', [True]); result = lab.scenario(name, mode)
                result['settlement_contract'] = result['actors']['nqc_executor']; result['architecture'] = 'C1'
                save(name, result); index.append({'scenario': name, 'status': 'REPRODUCED_003_CONTROL'})
                assert lab.rpc('evm_revert', [checkpoint]); lab.actors = actors
    if not args.only:
        with node(args.anvil, artifacts, pool_override=True, order='fees') as lab:
            lab.setup()
            result = run_case(lab, 'A3_priority_change', mode='priority_change')
            index.append({'scenario': result['scenario'], 'status': 'EVM_LOCAL_PASS'})
    save('run-index', {'runs': index, 'node_stopped': True, 'unsigned_only': True,
                        'fork': None, 'pool_balance_checks_disabled': True, 'EVM_balance_checks_disabled': False})

if __name__ == '__main__':
    main()
