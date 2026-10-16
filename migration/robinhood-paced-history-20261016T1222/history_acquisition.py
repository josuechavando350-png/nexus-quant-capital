"""One bounded history prepend, tail catch-up and three pinned observations."""
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
sys.path.insert(0,str(HERE.parent/'robinhood-paced-acquisition-20261016T1024'))
from pacing import Pacer, INTERVAL_NS
from backfill import merge


class Reader(TransportReader):
    def __init__(self, folder, policy, transports=None, factory=Transports, pacer=None):
        need(type(policy['max_requests']) is int and 1 <= policy['max_requests'] <= 512 and
             type(policy['max_run_seconds']) is int and 1 <= policy['max_run_seconds'] <= 900, 'BOUNDED_BUDGET')
        super().__init__(folder, policy, transports)
        self.mode, self.output_folder, self.epoch, self.factory = 'persistent', self.folder, 0, factory
        need(policy['minimum_start_interval_ns'] == INTERVAL_NS, 'PACING_POLICY')
        self.pacer, self.admissions, self.busy = pacer or Pacer(), [], False
        self.phase = 'verify'

    def request(self, method, params, label, creation=None):
        label = self.phase+'-'+label
        # A stopped reader is permanently latched; neither sleep nor another
        # transport/factory invocation is allowed after any failure.
        need(not self.stopped and not self.busy, 'REQUEST_BUDGET_OR_STOPPED')
        self.busy = True
        before = len(self.records)
        event = {'label':label, 'method':method, 'params':params,
                 'epoch':self.epoch, 'status':'pending'}
        self.admissions.append(event)
        try:
            need(self.count < self.policy['max_requests'], 'REQUEST_BUDGET_OR_STOPPED')
            self.pacer.admit(self.started_ns + self.policy['max_run_seconds']*10**9, event)
            return super().request(method, params, label, creation)
        except Exception as error:
            self.stopped = True
            event['exception'] = type(error).__name__
            event['reason'] = str(error) if isinstance(error, ValueError) and re.fullmatch('[A-Z0-9_]+',str(error)) else type(error).__name__
            raise
        finally:
            if len(self.records) > before:
                row = self.records[-1]
                self.pacer.record_start(row['started_ns'])
                row['admission_requested_ns'] = event['requested_ns']
                row['admission_due_ns'] = event['due_ns']
                row['admission_admitted_ns'] = event['admitted_ns']
                row['connection_epoch'] = self.epoch
                event.update(rpc_id=row['payload']['id'], started_ns=row['started_ns'],
                             status='failed' if 'exception' in row else 'dispatched')
                (self.folder/'requests.json').write_bytes(canonical(self.records))
            else:
                event['status'] = 'rejected_before_rpc'
            event['finished_ns'] = time.monotonic_ns()
            (self.folder/'admissions.json').write_bytes(canonical(self.admissions))
            self.busy = False

    def rotate_for_measurement(self):
        raise ValueError('NO_ROTATION_IN_HISTORY_PROTOCOL')


def source(policy, raw):
    need(hashlib.sha256(raw).hexdigest() == policy['source_file_sha256'], 'SOURCE_FILE_HASH')
    value = json.loads(raw)
    need(set(value) == {'state','sha256'} and registry.digest(value['state']) == value['sha256'] == policy['source_root'], 'SOURCE_ROOT')
    state = value['state']
    registry.validate(state, policy)
    need(state['status'] == 'valid_prefix', 'INVALID_SOURCE')
    need(policy['backfill_through_block'] == state['from_block']-1 and
         policy['backfill_from_block'] > 0 and
         policy['backfill_through_block']-policy['backfill_from_block']+1 == policy['backfill_blocks'] and
         0 < policy['backfill_blocks'] <= 400000 and policy['rounds'] == 3, 'FIXED_HISTORY_WINDOW')
    return state


def run(reader, journal, policy, registration, raw):
    existing = source(policy, raw)
    journal.append('registered', {'policy':policy,'registration_commit':registration,
                   'source_root':registry.digest(existing),'run_started_ns':reader.started_ns})
    path = reader.output_folder/'registry.json'
    registry.save(path, existing)
    need(qty(reader.call('eth_chainId', [], 'chain')) == policy['chain_id'], 'WRONG_CHAIN')
    canonical_check(reader, existing['checkpoint'], 'source-checkpoint')
    first,last = policy['backfill_from_block'],policy['backfill_through_block']
    boundary = get_header(reader,last,'backfill-boundary')
    need(boundary == existing['segments'][0]['start'],'SOURCE_BOUNDARY_REORG')
    reader.phase = 'history'
    older = registry.new(first)
    registry.save(reader.output_folder/'older-registry.json',older)
    journal.append('backfill_started',{'first':first,'last':last,'anchor':boundary})
    older = update_registry(reader,journal,policy,reader.output_folder/'older-registry.json',older,boundary)
    combined = merge(older,existing,policy)
    reader.phase = 'verify'
    canonical_check(reader,existing['checkpoint'],'source-after-history')
    registry.save(reader.output_folder/'merged-before-catchup.json',combined)
    registry.save(path,combined)
    journal.append('backfill_merged',{'older_registry_sha256':registry.digest(older),
                   'merged_registry_sha256':registry.digest(combined),'source_registry_sha256':registry.digest(existing)})
    reader.phase = 'catchup'
    head = get_header(reader, 'latest', 'index-head')
    anchor = get_header(reader, head['number']-policy['confirmation_buffer_blocks'], 'index-anchor')
    journal.append('catchup_started', {'anchor':anchor,'prior_through_block':existing['through_block']})
    state = update_registry(reader,journal,policy,path,combined,anchor)
    # A zero-length update must still leave a persisted, checked prefix.
    registry.save(path,state)
    reader.phase = 'authenticate'
    authenticate(reader,anchor)
    cohort = registry.freeze(state, anchor['number'], policy)
    (reader.output_folder/'cohort.json').write_bytes(canonical(cohort))
    journal.append('cohort_frozen',cohort)
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
