"""Offline source/context audit. No state transition, RPC or historical proof.

Text anchors guard the reviewed source relationships; they do not execute Go.
Header checks authenticate bytes relative to the already observed hashes only.
"""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / 'nqc-037-historical-state'
MAP = HERE.parent / 'nqc-041-tx0-storage-map'
sys.path.insert(0, str(PREVIOUS / 'src'))
sys.path.insert(0, str(MAP))
import verify
import storage_map as slots

FILTERED = '0xa4b0500000000000000000000000000000000001'
SOURCE_PATHS = {
    'block': HERE / 'vendor/nitro__arbos__block_processor.go',
    'tx': HERE / 'vendor/nitro__arbos__tx_processor.go',
    'transition': HERE / 'vendor/go-ethereum__core__state_transition.go',
    'filtered': HERE / 'vendor/nitro__arbos__filteredTransactions__state.go',
    'signer': HERE / 'vendor/go-ethereum__core__types__arbitrum_signer.go',
    'arbos': PREVIOUS / 'vendor/nitro__arbos__arbosState__arbosstate.go',
    'storage': PREVIOUS / 'vendor/nitro__arbos__storage__storage.go',
    'model': MAP / 'vendor/nitro__arbos__l2pricing__model.go',
    'fees': MAP / 'vendor/nitro__arbos__l2pricing__multi_gas_fees.go',
    'processor': PREVIOUS / 'vendor/go-ethereum__core__state_processor.go',
}


def function(text, signature):
    start = text.index(signature)
    end = text.find('\nfunc ', start + len(signature))
    return text[start:] if end < 0 else text[start:end]


def ordered(text, tokens):
    cursor = 0
    for token in tokens:
        index = text.find(token, cursor)
        if index < 0:
            raise ValueError('missing or reordered source anchor: ' + token)
        cursor = index + len(token)


def source_contract(overrides=None):
    texts = {name: path.read_text() for name, path in SOURCE_PATHS.items()}
    texts.update(overrides or {})
    specifications = [
        ('prefix_order', 'block', 'func ProduceBlockAdvanced(', [
            'arbosState.OpenSystemArbosState(statedb, nil, false)',
            'err = l2Pricing.CommitMultiGasFees()', 'baseFee, err := l2Pricing.BaseFeeWei()',
            'header := createNewHeader(', 'startTx := InternalTxStartBlock(',
            'firstTx := types.NewTx(startTx)', 'if firstTx != nil {',
            'core.ApplyTransactionWithResultFilter(']),
        ('header_fee_capture', 'block', 'func createNewHeader(', [
            'if timestamp < prevHeader.Time {', 'timestamp = prevHeader.Time',
            'BaseFee:     baseFee,']),
        ('conditional_rotation', 'model', 'func (ps *L2PricingState) CommitMultiGasFees()', [
            'gasModel, err := ps.GasModelToUse()', 'if err != nil {', 'return err',
            'if gasModel != GasModelMultiGasConstraints {', 'return nil',
            'return ps.multiGasFees.CommitNextToCurrent()']),
        ('rotation_direction', 'fees', 'func (bf *MultiGasFees) CommitNextToCurrent()', [
            'for i := range int(multigas.NumResourceKind)', 'cur, err := bf.next[i].Get()',
            'bf.current[i].SetChecked(cur)']),
        ('arbos_open_nonce', 'storage', 'func KVStorage(', [
            'statedb.SetNonce(account, 1, tracing.NonceChangeUnspecified)', 'return &Storage{']),
        ('arbos_constructor', 'arbos', 'func OpenArbosState(', [
            'backingStorage := storage.NewGeth(stateDB, burner)',
            'arbosVersion, err := backingStorage.GetUint64ByUint64(',
            'openFilteredTransactions(arbosVersion, stateDB, burner)']),
        ('filtered_open_guard', 'arbos', 'func openFilteredTransactions(', [
            'arbosVersion >= params.ArbosVersion_TransactionFiltering',
            'return filteredTransactions.Open(stateDB, burner)']),
        ('filtered_storage', 'filtered', 'func Open(', [
            'storage.FilteredTransactionsStorage(statedb, burner)']),
        ('filtered_account', 'storage', 'func FilteredTransactionsStorage(', [
            'return KVStorage(statedb, burner, types.FilteredTransactionsStateAddress)']),
        ('internal_early_return', 'tx', 'func (p *TxProcessor) StartTxHook()', [
            'case *types.ArbitrumInternalTx:', 'if p.msg.From != arbosAddress {',
            'err = ApplyInternalTxUpdate(tx, p.state, evm)',
            'return true, multigas.ZeroGas(), err, nil']),
        ('geth_early_exit', 'transition', 'func (st *stateTransition) execute()', [
            'st.evm.ProcessingHook.StartTxHook()', 'if endTxNow {',
            'return &ExecutionResult{', 'st.preCheck()', 'st.evm.ProcessingHook.EndTxHook(']),
        ('transaction_finalisation', 'processor', 'func ApplyTransactionWithEVM(', [
            'result, err = ApplyMessage(', 'if resultFilter != nil {',
            'if evm.ChainConfig().IsByzantium(blockNumber) {', 'evm.StateDB.Finalise(true)']),
    ]
    result = []
    for label, source, signature, tokens in specifications:
        body = function(texts[source], signature)
        ordered(body, tokens)
        result.append({'check': label, 'source': str(SOURCE_PATHS[source].relative_to(HERE.parent)),
                       'function': signature, 'ordered_anchors': tokens})
    assert ('FilteredTransactionsStateAddress = common.HexToAddress("' + FILTERED.upper().replace('0X', '0x') + '")') in texts['signer']
    return result


def check_sources():
    for row in verify.read_json(HERE / 'SOURCES.json')['sources']:
        data = (HERE / row['path']).read_bytes()
        digest = hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()
        if digest != row['git_blob_sha'] or len(data) != row['size_bytes']:
            raise ValueError('vendored source identity mismatch')


def fee_rotation_layout(version, single_length=None, multi_length=None):
    """Hypothetical branch layout only; inputs are not authenticated here."""
    model = slots.pricing_model(version, single_length, multi_length)
    if model is None:
        raise ValueError('parent model unknown; missing length is not zero')
    if model != 'multi':
        return []
    fees = slots.fee_slots()
    return [{'resource': i, 'read_next': fees[f'next_{i}'], 'write_current': fees[f'current_{i}']}
            for i in range(slots.NUM_RESOURCE_KIND)]


def header_context(parent, target):
    verify.validate_header(parent, verify.PARENT_HASH, verify.PARENT_NUMBER)
    verify.validate_header(target, verify.TARGET_HASH, verify.TARGET_NUMBER)
    verify.require(target['parentHash'] == parent['hash'], 'parent mismatch')
    return {
        'parent_number': verify.PARENT_NUMBER, 'target_number': verify.TARGET_NUMBER,
        'parent_header_base_fee_wei': verify.quantity(parent['baseFeePerGas']),
        'target_header_base_fee_wei': verify.quantity(target['baseFeePerGas']),
        'parent_header_arbos_version': int.from_bytes(verify.data_hex(parent['mixHash'], 32)[16:24], 'big'),
        'target_header_arbos_version': int.from_bytes(verify.data_hex(target['mixHash'], 32)[16:24], 'big'),
        'timestamp_delta': verify.quantity(target['timestamp']) - verify.quantity(parent['timestamp']),
        'target_gas_limit': verify.quantity(target['gasLimit']),
        'hash_checks_relative_to_observations_only': True,
    }


def review():
    check_sources()
    context = header_context(*[verify.read_json(PREVIOUS / f'inputs/{n}-header.json')['result']
                               for n in ('parent', 'target')])
    diagnostic = verify.read_json(PREVIOUS / 'inputs/augmented-prestate.json')['result']
    plan = verify.read_json(HERE.parent / 'nqc-038-archive-access/TRIPORT_PLAN.json')
    controls = slots.control_slots()
    dependencies = {name: controls[name] for name in [
        'arbos_version', 'single_constraints_length', 'multi_constraints_length',
        'l2_base_fee', 'l2_per_block_gas_limit']}
    dependencies['brotli_compression_level'] = slots.slot((), 7)
    arbos_proof = next(x['request'] for x in plan['logical_requests'] if x['purpose'] == 'arbos_proof')
    return {
        'scope': 'pinned candidate source review; NOT Go execution or a complete witness',
        'source_checks': source_contract(), 'observed_header_context': context,
        'parent_pricing_model': 'UNKNOWN: parent constraint lengths not acquired',
        'known_prefix_slot_candidates': dependencies,
        'prefix_candidates_missing_from_eight_read_plan': {
            name: slot for name, slot in dependencies.items() if slot not in arbos_proof['params'][1]},
        'source_implied_parent_base_fee_not_a_storage_proof': {
            'account': slots.ARBOS, 'slot': controls['l2_base_fee'],
            'expected_wei_if_candidate_semantics_apply': context['target_header_base_fee_wei'],
            'proof_acquired': False, 'diagnostic_value': diagnostic[slots.ARBOS]['storage'].get(controls['l2_base_fee'])},
        'nonce_assignments_on_open': [
            {'account': slots.ARBOS, 'assigned_nonce': 1, 'diagnostic_nonce': diagnostic[slots.ARBOS].get('nonce')},
            {'account': FILTERED, 'assigned_nonce': 1, 'condition': 'parent ArbOS >= 60',
             'present_in_diagnostic': FILTERED in diagnostic,
             'requested_in_eight_read_plan': any(x['request']['method'] == 'eth_getProof' and
                x['request']['params'][0].lower() == FILTERED for x in plan['logical_requests'])}],
        'conditional_multigas_rotation_layout': fee_rotation_layout(61, None, 1),
        'rotation_layout_is_hypothetical_not_observed': True,
        'rpc_requests_sent': 0, 'historical_proofs_acquired': 0,
        'historical_binary_identity_verified': False, 'complete_access_list': False,
        'commercial_admission': False,
    }


if __name__ == '__main__':
    (HERE / 'PREFIX_REVIEW.json').write_text(json.dumps(review(), indent=2, sort_keys=True) + '\n')
