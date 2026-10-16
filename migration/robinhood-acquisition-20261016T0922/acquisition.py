"""Pinned PR15 transport plus tail-only enrollment and complete acquisition."""
import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import re
import sys
import time

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent/'robinhood-transport-benchmark-20261016T0821'
sys.path.insert(0, str(PRIOR))
from transport import (Reader as TransportReader, Transports, need, canonical, qty,
                       registry, Journal, lens)
from collect import get_header, canonical_check, update_registry, authenticate


class Reader(TransportReader):
    def __init__(self, folder, policy, transports=None, factory=Transports):
        need(type(policy['max_requests']) is int and 1 <= policy['max_requests'] <= 512 and
             type(policy['max_run_seconds']) is int and 1 <= policy['max_run_seconds'] <= 900, 'BOUNDED_BUDGET')
        super().__init__(folder, policy, transports)
        self.mode, self.output_folder, self.epoch, self.factory = 'persistent', self.folder, 0, factory

    def rotate_for_measurement(self):
        need(not self.stopped and self.epoch == 0 and self.count > 0, 'ONE_HEALTHY_PREREGISTERED_ROTATION')
        self.transports.close()
        self.transports = self.factory()
        self.epoch = 1
        return {'rpc_calls_before':self.count,'successful_response_bytes_before':self.total,
                'run_started_ns':self.started_ns,'epoch':self.epoch}


def source(policy, raw):
    need(hashlib.sha256(raw).hexdigest() == policy['source_file_sha256'], 'SOURCE_FILE_HASH')
    value = json.loads(raw)
    need(set(value) == {'state','sha256'} and registry.digest(value['state']) == value['sha256'] == policy['source_root'], 'SOURCE_ROOT')
    state = value['state']
    registry.validate(state, policy)
    need(state['status'] == 'valid_prefix', 'INVALID_SOURCE')
    return state


def run(reader, journal, policy, registration, raw):
    existing = source(policy, raw)
    journal.append('registered', {'policy':policy,'registration_commit':registration,
                   'source_root':registry.digest(existing),'run_started_ns':reader.started_ns})
    path = reader.output_folder/'registry.json'
    registry.save(path, existing)
    need(qty(reader.call('eth_chainId', [], 'chain')) == policy['chain_id'], 'WRONG_CHAIN')
    canonical_check(reader, existing['segments'][0]['start'], 'source-start')
    head = get_header(reader, 'latest', 'index-head')
    anchor = get_header(reader, head['number']-policy['confirmation_buffer_blocks'], 'index-anchor')
    journal.append('catchup_started', {'anchor':anchor,'prior_through_block':existing['through_block']})
    state = update_registry(reader,journal,policy,path,existing,anchor)
    # A zero-length update must still leave a persisted, checked prefix.
    registry.save(path,state)
    authenticate(reader,anchor)
    cohort = registry.freeze(state, anchor['number'], policy)
    (reader.output_folder/'cohort.json').write_bytes(canonical(cohort))
    journal.append('cohort_frozen',cohort)
    journal.append('measurement_session_started',reader.rotate_for_measurement())
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
                'connection_epoch':1,'planned_start':'cold' if index == 0 else 'reuse_eligible',
                'head_transport':head_row['transport'],'view_transport':view_row['transport'],
                'canonical_transport':check_row['transport'],
                'header_ms':(head_row['received_ns']-head_row['started_ns'])/1e6,
                'view_input_ms':(view_row['received_ns']-view_row['started_ns'])/1e6,
                'request_to_inputs_ms':(view_row['received_ns']-head_row['started_ns'])/1e6,
                'request_to_verified_ms':(verified-head_row['started_ns'])/1e6,
                'received_head_to_verified_ms':(verified-head_row['received_ns'])/1e6,
                'header_timestamp_age_at_final_response_ms':check_row['received_wall_ns']/1e6-block['timestamp']*1000,
                'unindexed_tail_blocks':block['number']-state['through_block'],
                'within_assumed_1000ms':verified-head_row['started_ns'] <= policy['freshness_budget_ms_assumed']*1e6}
        journal.append('observation_completed',data)
        prior = block
    journal.append('completed',{'rpc_calls':reader.count,'http_requests':len(reader.records),
                   'route_simulations':0,'live_broadcasts':0,'realized_profit':None})


def safe_stop(reader,journal,error):
    reason = str(error) if isinstance(error, ValueError) and re.fullmatch('[A-Z0-9_]+',str(error)) else type(error).__name__
    journal.append('stopped',{'exception':type(error).__name__,'reason':reason,'rpc_calls':reader.count,
                   'http_requests':len(reader.records),'realized_profit':None})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--registration-commit',required=True)
    args = parser.parse_args()
    need(re.fullmatch('[0-9a-f]{40}',args.registration_commit),'REGISTRATION_COMMIT')
    for requirement in (PRIOR/'requirements.txt').read_text().splitlines():
        name,expected = requirement.split('==')
        need(version(name) == expected,'DEPENDENCY_VERSION')
    lock = json.loads((HERE/'registration-sources.json').read_text())
    for name,sha in lock['files'].items():
        need(hashlib.sha256((HERE/name).read_bytes()).hexdigest() == sha,'REGISTERED_SOURCE_CHANGED')
    policy = json.loads((HERE/'policy.json').read_text())
    raw = (HERE.parent.parent/policy['source_path']).read_bytes()
    source(policy,raw)
    reader = Reader(args.out,policy); journal = Journal(reader.folder)
    (reader.folder/'source-registry.json').write_bytes(raw)
    status = 'completed'
    try:
        run(reader,journal,policy,args.registration_commit,raw)
    except Exception as error:
        safe_stop(reader,journal,error); status = 'stopped'
    finally:
        reader.transports.close()
    print(json.dumps({'status':status,'rpc_calls':reader.count,'http_requests':len(reader.records),
                     'elapsed_seconds':(time.monotonic_ns()-reader.started_ns)/1e9}),flush=True)
    return int(status != 'completed')


if __name__ == '__main__':
    raise SystemExit(main())
