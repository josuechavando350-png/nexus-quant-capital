"""PR19 observation block, unchanged; acquisition includes initial admission wait."""
from history_acquisition import need, lens, canonical_check, get_header

def observe(reader,journal,policy,state,anchor,cohort):
    reader.phase = 'observe'
    journal.append('measurement_session_started',{'rpc_calls_before':reader.count,
                   'successful_response_bytes_before':reader.total,'run_started_ns':reader.started_ns,'epoch':0})
    prior = None
    for index in range(policy['rounds']):
        block = get_header(reader,'latest',f'r{index}-head')
        head_row = reader.records[-1]
        need(block['number'] > anchor['number'], 'HEAD_NOT_AFTER_ANCHOR')
        if prior is not None:
            need(block['number'] >= prior['number'] and
                 (block['number'] != prior['number'] or block == prior), 'HEAD_REGRESSION_OR_REORG')
        repeated = prior is not None and block['number'] == prior['number']
        output = reader.creation(block,cohort['addresses'],f'r{index}-view')
        view_row = reader.records[-1]
        derived = lens.parse(block,cohort['addresses'],output,policy)
        canonical_check(reader,block,f'r{index}-canonical')
        verified = reader.verified()
        check_row = reader.records[-1]
        data = {'round':index,'block':block,'state':derived,'repeated_head':repeated,
                'connection_epoch':0,'planned_start':'persistent_after_indexing',
                'head_transport':head_row['transport'],'view_transport':view_row['transport'],
                'canonical_transport':check_row['transport'],
                'header_ms':(head_row['received_ns']-head_row['started_ns'])/1e6,
                'view_input_ms':(view_row['received_ns']-view_row['started_ns'])/1e6,
                'request_to_inputs_ms':(view_row['received_ns']-head_row['started_ns'])/1e6,
                'request_to_verified_ms':(verified-head_row['started_ns'])/1e6,
                'header_admission_wait_ms':(head_row['started_ns']-head_row['admission_requested_ns'])/1e6,
                'admission_to_inputs_ms':(view_row['received_ns']-head_row['admission_requested_ns'])/1e6,
                'admission_to_verified_ms':(verified-head_row['admission_requested_ns'])/1e6,
                'header_admission_requested_ns':head_row['admission_requested_ns'],
                'verified_ns':verified,
                'received_head_to_verified_ms':(verified-head_row['received_ns'])/1e6,
                'header_timestamp_age_at_final_response_ms':check_row['received_wall_ns']/1e6-block['timestamp']*1000,
                'unindexed_tail_blocks':block['number']-state['through_block'],
                'within_assumed_1000ms':verified-head_row['admission_requested_ns'] <= policy['freshness_budget_ms_assumed']*1e6}
        journal.append('observation_completed',data)
        prior = block
    journal.append('completed',{'rpc_calls':reader.count,'http_requests':len(reader.records),
                   'route_simulations':0,'live_broadcasts':0,'realized_profit':None})
