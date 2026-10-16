#!/usr/bin/env python3
"""Pure paper-decision gate; it cannot sign, send or grant sponsorship.

Decision inputs must already be logged at the decision's monotonic timestamp.
Economic inputs and latency limits are supplied explicitly; unknown readiness
is a rejection. A historical replay alone never produces a production PASS.
"""
from economics import decimal


def assess(record):
    required = {'source_block', 'source_hash', 'source_time', 'received_ns', 'decision_ns',
                'simulation_finished_ns', 'prediction_time', 'input_max_block',
                'input_max_time', 'max_age_ns', 'horizon_seconds', 'history_selected',
                'simulation_success', 'expected_net_usdg', 'prepaid_capacity_wei',
                'prefund_wei', 'bundler_admission_proven', 'validation_expiry_proven',
                'nonrecourse_funding_proven', 'latency_budget_proven'}
    if set(record) != required:
        raise ValueError('complete, explicit paper-decision schema required')
    ints = required - {'source_hash', 'history_selected', 'simulation_success', 'expected_net_usdg',
                       'bundler_admission_proven', 'validation_expiry_proven',
                       'nonrecourse_funding_proven', 'latency_budget_proven'}
    if any(type(record[k]) is not int or record[k] < 0 for k in ints):
        raise ValueError('nonnegative integer times, amounts and heights required')
    flags = {'history_selected', 'simulation_success', 'bundler_admission_proven',
             'validation_expiry_proven', 'nonrecourse_funding_proven', 'latency_budget_proven'}
    if any(type(record[k]) is not bool for k in flags):
        raise ValueError('explicit boolean readiness required')
    h = record['source_hash']
    if not isinstance(h, str) or len(h) != 66 or not h.startswith('0x'):
        raise ValueError('source block hash required')
    try:
        bytes.fromhex(h[2:])
    except ValueError as error:
        raise ValueError('source block hash required') from error
    reasons = []
    if record['history_selected']:
        reasons.append('HINDSIGHT_SELECTED_CASE')
    if record['input_max_block'] > record['source_block'] or record['input_max_time'] > record['source_time']:
        reasons.append('FUTURE_INPUT')
    if not record['received_ns'] <= record['simulation_finished_ns'] <= record['decision_ns']:
        reasons.append('DECISION_BEFORE_INPUT_READY')
    if record['decision_ns'] - record['received_ns'] > record['max_age_ns']:
        reasons.append('STALE_SNAPSHOT')
    if not 0 <= record['prediction_time'] - record['source_time'] <= record['horizon_seconds']:
        reasons.append('OUTSIDE_PROJECTION_HORIZON')
    if not record['simulation_success']:
        reasons.append('SIMULATION_FAILED')
    if decimal(record['expected_net_usdg']) <= 0:
        reasons.append('NONPOSITIVE_EXPECTED_MARGIN')
    if record['prefund_wei'] <= 0 or record['prepaid_capacity_wei'] < record['prefund_wei']:
        reasons.append('INSUFFICIENT_PREPAID_CAPITAL')
    for name in ['bundler_admission_proven', 'validation_expiry_proven', 'nonrecourse_funding_proven', 'latency_budget_proven']:
        if not record[name]:
            reasons.append(name.upper())
    return {'paper_candidate': not reasons, 'reasons': reasons,
            'broadcast_enabled': False, 'production_authorization': False}
