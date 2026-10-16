"""Replay tail updates and complete acquisition, including partial file state."""
import argparse
import hashlib
import json
from pathlib import Path
from contextlib import redirect_stdout
import io
import tempfile
from types import SimpleNamespace

from recovery import HERE, need, canonical, Reader, registry, run
from pacing import INTERVAL_NS
from transport import decode, MAX_REPLY, MAX_TOTAL


class RecordedTransportStop(Exception):
    pass


class Replay(Reader):
    def __init__(self, folder, rows, policy, started, terminal, admissions):
        self.folder, self.rows, self.policy = folder, rows, policy
        self.records, self.count, self.mode, self.epoch = [], 0, 'persistent', 0
        self.started_ns, self.terminal, self.total = started, terminal, 0
        self.admissions = admissions
        self.phase = 'verify'

    def rotate_for_measurement(self):
        need(self.epoch == 0 and self.count > 0,'REPLAY_ROTATION')
        self.epoch = 1
        return {'rpc_calls_before':self.count,'successful_response_bytes_before':self.total,
                'run_started_ns':self.started_ns,'epoch':self.epoch}

    def verified(self):
        row = self.records[-1]
        need(row.get('verified_ns', 0) >= row['finished_ns'], 'VERIFICATION_CLOCK')
        return row['verified_ns']

    def request(self, method, params, label, creation=None):
        label = self.phase+'-'+label
        if self.count == len(self.rows) and self.terminal['kind'] == 'stopped':
            reason = self.terminal['data']['reason']
            if len(self.admissions) > len(self.rows):
                denied = self.admissions[-1]
                need((denied['label'],denied['method'],denied['params'],denied['epoch']) ==
                     (label,method,params,self.epoch), 'REPLAY_ADMISSION_DIFFERS')
                need(reason == denied['reason'], 'ADMISSION_STOP_REASON')
                if reason == 'PACING_TIME_BUDGET':
                    need(denied['due_ns'] >= denied['deadline_ns'], 'UNEXPLAINED_PACING_BUDGET')
                    raise RecordedTransportStop(reason)
                if reason == 'PACING_EARLY_WAKE':
                    need(denied['admitted_ns'] < denied['due_ns'], 'UNEXPLAINED_EARLY_WAKE')
                    raise RecordedTransportStop(reason)
            if reason == 'REQUEST_BUDGET_OR_STOPPED':
                need(self.count >= self.policy['max_requests'], 'UNEXPLAINED_REQUEST_BUDGET')
                raise RecordedTransportStop(reason)
            if reason == 'TIME_BUDGET':
                need(self.terminal['recorded_ns']-self.started_ns >= self.policy['max_run_seconds']*10**9, 'UNEXPLAINED_TIME_BUDGET')
                raise RecordedTransportStop(reason)
        need(self.count < len(self.rows), 'UNEXPLAINED_MISSING_REQUEST')
        row = self.rows[self.count]
        self.count += 1
        expected = {'jsonrpc': '2.0', 'id': self.count, 'method': method, 'params': params}
        need(row['payload'] == expected and row['label'] == label and row['mode'] == self.mode and
             row['connection_epoch'] == self.epoch, 'REPLAY_REQUEST_DIFFERS')
        self.records.append(row)
        raw = (self.folder/row['response_file']).read_bytes() if 'response_file' in row else None
        if row.get('response_complete') and raw is not None:
            self.total += len(raw)
        if 'exception' in row:
            if row.get('response_complete'):
                try:
                    decode(expected, raw)
                except Exception as error:
                    need(type(error).__name__ == row['exception'], 'RPC_EXCEPTION_DIFFERS')
                else:
                    need(len(raw) > MAX_REPLY or self.total > MAX_TOTAL, 'UNEXPLAINED_SUCCESSFUL_RESPONSE_ERROR')
            raise RecordedTransportStop(row['exception'])
        need(raw is not None and row['response_complete'] is True and row['transport']['status'] == 200, 'MISSING_SUCCESS_RESPONSE')
        return decode(expected, raw)[0]


def audit(folder, expected_policy=None):
    folder = Path(folder)
    journal = [json.loads(line) for line in (folder/'journal.jsonl').read_text().splitlines()]
    need(journal and journal[0]['kind'] == 'registered' and journal[-1]['kind'] in ('completed', 'stopped'), 'JOURNAL_TERMINAL')
    previous = '0'*64
    for index, row in enumerate(journal):
        unsigned = {k: v for k, v in row.items() if k != 'sha256'}
        need(row['sequence'] == index and row['previous_sha256'] == previous and
             hashlib.sha256(canonical(unsigned)).hexdigest() == row['sha256'], 'JOURNAL_HASH_CHAIN')
        if index:
            need(row['recorded_ns'] >= journal[index-1]['recorded_ns'], 'JOURNAL_CLOCK')
        previous = row['sha256']
    registered = journal[0]['data']
    policy = expected_policy or json.loads((HERE/'policy.json').read_text())
    need(registered['policy'] == policy, 'REGISTERED_POLICY_DIFFERS')
    rows = json.loads((folder/'requests.json').read_text()) if (folder/'requests.json').exists() else []
    need(len(rows) <= policy['max_requests'] and journal[-1]['data']['rpc_calls'] == len(rows) == journal[-1]['data']['http_requests'], 'REQUEST_COUNTS')
    total = 0
    for index, row in enumerate(rows):
        need(journal[0]['recorded_ns'] <= row['started_ns'] <= row['finished_ns'] <= journal[-1]['recorded_ns'], 'REQUEST_CLOCK')
        if index:
            need(row['started_ns'] >= rows[index-1]['finished_ns'], 'PARALLEL_REQUESTS')
            if 'verified_ns' in rows[index-1]:
                need(row['started_ns'] >= rows[index-1]['verified_ns'], 'VERIFICATION_CLOCK')
        if 'received_ns' in row:
            need(row['started_ns'] <= row['received_ns'] <= row['finished_ns'], 'RECEIVE_CLOCK')
        if 'exception' in row:
            need(index == len(rows)-1, 'REQUEST_AFTER_FAILURE')
        if 'response_file' in row:
            name = row['response_file']
            need(Path(name).name == name, 'RESPONSE_PATH')
            raw = (folder/name).read_bytes()
            need(hashlib.sha256(raw).hexdigest() == row['response_sha256'] and len(raw) == row['response_bytes'], 'RESPONSE_HASH')
            need(len(raw) <= MAX_REPLY+1, 'RESPONSE_CAP')
            total += len(raw)
    need(total <= MAX_TOTAL+MAX_REPLY+1, 'TOTAL_BYTES')
    need(registered['run_started_ns'] <= journal[0]['recorded_ns'], 'RUN_START_CLOCK')
    admissions = json.loads((folder/'admissions.json').read_text()) if (folder/'admissions.json').exists() else []
    need(len(rows) <= len(admissions) <= len(rows)+1, 'ADMISSION_COUNTS')
    need(policy['minimum_start_interval_ns'] == INTERVAL_NS, 'PACING_POLICY')
    deadline = registered['run_started_ns'] + policy['max_run_seconds']*10**9
    for index, attempt in enumerate(admissions):
        if index:
            need(admissions[index-1]['status'] == 'dispatched', 'ADMISSION_AFTER_FAILURE')
        need(journal[0]['recorded_ns'] <= attempt['finished_ns'] <= journal[-1]['recorded_ns'], 'ADMISSION_CLOCK')
        if 'requested_ns' in attempt:
            requested = attempt['requested_ns']
            due = requested if index == 0 else max(requested, rows[index-1]['started_ns']+INTERVAL_NS)
            need(attempt['due_ns'] == due and attempt['deadline_ns'] == deadline, 'ADMISSION_DUE_OR_DEADLINE')
            need(journal[0]['recorded_ns'] <= requested <= attempt['finished_ns'], 'ADMISSION_REQUEST_CLOCK')
            if index:
                need(requested >= admissions[index-1]['finished_ns'], 'ADMISSION_PARALLEL')
        if index < len(rows):
            row = rows[index]
            need(attempt['rpc_id'] == row['payload']['id'] and attempt['started_ns'] == row['started_ns'] and
                 (attempt['method'],attempt['params'],attempt['label'],attempt['epoch']) ==
                 (row['payload']['method'],row['payload']['params'],row['label'],row['connection_epoch']), 'ADMISSION_RPC_DIFFERS')
            need(attempt['requested_ns'] == row['admission_requested_ns'] and
                 attempt['due_ns'] == row['admission_due_ns'] and
                 attempt['admitted_ns'] == row['admission_admitted_ns'], 'ADMISSION_ROW_DIFFERS')
            need(attempt['due_ns'] <= attempt['admitted_ns'] <= row['started_ns'] < deadline and
                 row['finished_ns'] <= attempt['finished_ns'], 'DISPATCH_ADMISSION_CLOCK')
            need(attempt['status'] == ('failed' if 'exception' in row else 'dispatched'), 'ADMISSION_STATUS')
            if 'exception' in row:
                need(attempt['exception'] == row['exception'] and attempt['reason'] == journal[-1]['data']['reason'], 'ADMISSION_EXCEPTION')
            if index:
                need(row['started_ns']-rows[index-1]['started_ns'] >= INTERVAL_NS, 'GLOBAL_START_GAP')
        else:
            need(journal[-1]['kind'] == 'stopped' and attempt['status'] == 'rejected_before_rpc' and
                 'rpc_id' not in attempt and attempt['reason'] == journal[-1]['data']['reason'], 'ADMISSION_REJECTION')
    replay = Replay(folder, rows, policy, registered['run_started_ns'], journal[-1], admissions)
    cursor = 0
    def emit(kind, data):
        nonlocal cursor
        need(cursor < len(journal) and journal[cursor]['kind'] == kind and journal[cursor]['data'] == data, 'JOURNAL_REPLAY_DIFFERS')
        cursor += 1
    error = None
    with tempfile.TemporaryDirectory() as temporary:
        replay.output_folder = Path(temporary)
        try:
            with redirect_stdout(io.StringIO()):
                run(replay, SimpleNamespace(append=emit), policy, registered['registration_commit'], (folder/'source-registry.json').read_bytes(), (folder/'older-source-registry.json').read_bytes())
        except Exception as caught:
            error = caught
        for filename in ('registry.json','cohort.json','older-registry.json','merged-before-catchup.json'):
            generated, saved = replay.output_folder/filename, folder/filename
            need(generated.exists() == saved.exists(), 'PERSISTED_FILE_PRESENCE')
            if generated.exists():
                need(generated.read_bytes() == saved.read_bytes(), 'PERSISTED_FILE_DIFFERS')
    if journal[-1]['kind'] == 'completed':
        if error:
            raise error
        need(cursor == len(journal) and replay.count == len(rows), 'INCOMPLETE_REPLAY')
    else:
        need(error is not None and cursor == len(journal)-1 and replay.count == len(rows), 'STOP_REPLAY_DIFFERS')
        # Structural corruption is not accepted as an observed capture interruption.
        if not isinstance(error, RecordedTransportStop):
            reason = journal[-1]['data']['reason']
            need(str(error) == reason and reason not in {'JOURNAL_REPLAY_DIFFERS', 'REPLAY_REQUEST_DIFFERS',
                 'UNEXPLAINED_MISSING_REQUEST', 'RESPONSE_HASH'}, 'STOP_REASON_DIFFERS')
    reads = [r['data'] for r in journal if r['kind'] == 'observation_completed']
    cohort = next((r['data'] for r in journal if r['kind'] == 'cohort_frozen'), None)
    saved_registry = registry.load(folder/'registry.json',policy)
    events = registry.validate(saved_registry,policy)
    initial = json.loads((folder/'source-registry.json').read_text())['state']
    offset = next((i for i,s in enumerate(saved_registry['segments']) if s['first']==initial['from_block']),None)
    need(offset is not None,'SOURCE_SEGMENTS_MISSING')
    saved_source = saved_registry['segments'][offset:offset+len(initial['segments'])]
    strip = lambda s:{k:v for k,v in s.items() if k!='previous_segment_sha256'}
    need([strip(s) for s in saved_source] == [strip(s) for s in initial['segments']], 'SOURCE_SEGMENTS_CHANGED')
    merged = any(r['kind']=='history_recovered' for r in journal)
    older_path=folder/'older-registry.json'
    older=registry.load(older_path,policy) if older_path.exists() else None
    older_raw = (folder/'older-source-registry.json').read_bytes()
    need(older_path.read_bytes() == older_raw, 'OLDER_SOURCE_BYTES_CHANGED')
    if merged:
        prefix = saved_registry['segments'][:len(older['segments'])]
        need(prefix == older['segments'], 'OLDER_SEGMENTS_CHANGED')
    return {'status': journal[-1]['kind'], 'rpc_calls': len(rows), 'http_requests': len(rows),
            'admission_attempts':len(admissions),
            'minimum_start_gap_ms':min((b['started_ns']-a['started_ns'])/1e6 for a,b in zip(rows,rows[1:])) if len(rows)>1 else None,
            'admission_wait_ms':sum((r['started_ns']-r['admission_requested_ns'])/1e6 for r in rows),
            'acquisition_admission_intervals_ms':[(b['header_admission_requested_ns']-a['header_admission_requested_ns'])/1e6 for a,b in zip(reads,reads[1:])],
            'response_bytes': total, 'observations': reads, 'cohort':cohort,
            'source_registry_sha256':registered['source_root'],
            'history_recovered':merged,'older_registry':{'sha256':registry.digest(older),
                'from_block':older['from_block'],'through_block':older['through_block'],
                'status':older['status'],'events':sum(len(s['events']) for s in older['segments'])} if older else None,
            'registry':{'sha256':registry.digest(saved_registry),'status':saved_registry['status'],
                'from_block':saved_registry['from_block'],'through_block':saved_registry['through_block'],
                'added_tail_blocks':saved_registry['through_block']-initial['through_block'],
                'added_history_blocks':initial['from_block']-saved_registry['from_block'],
                'added_blocks':saved_registry['through_block']-initial['through_block']+initial['from_block']-saved_registry['from_block'],
                'blocks':saved_registry['through_block']-saved_registry['from_block']+1,
                'events':len(events),'added_events':len(events)-sum(len(s['events']) for s in initial['segments']),
                'source_segments_preserved':True},
            'started_utc_ns': journal[0]['recorded_wall_ns'], 'ended_utc_ns': journal[-1]['recorded_wall_ns'],
            'elapsed_seconds': (journal[-1]['recorded_ns']-journal[0]['recorded_ns'])/1e9,
            'profitability_measured': False, 'realized_profit': None, 'live_broadcasts': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.folder)
    args.out.write_bytes(canonical(result))
    print(json.dumps({k: v for k, v in result.items() if k != 'observations'}))
