"""Replay the registered transport control flow without networking."""
import argparse
import hashlib
import json
from pathlib import Path

from transport import HERE, need, canonical, Reader, decode, MAX_REPLY, MAX_TOTAL
from benchmark import run


class RecordedTransportStop(Exception):
    pass


class Replay(Reader):
    def __init__(self, folder, rows, policy, started, terminal):
        self.folder, self.rows, self.policy = folder, rows, policy
        self.records, self.count, self.mode = [], 0, 'legacy'
        self.started_ns, self.terminal, self.total = started, terminal, 0

    def verified(self):
        row = self.records[-1]
        need(row.get('verified_ns', 0) >= row['finished_ns'], 'VERIFICATION_CLOCK')
        return row['verified_ns']

    def request(self, method, params, label, creation=None):
        if self.count == len(self.rows) and self.terminal['kind'] == 'stopped':
            reason = self.terminal['data']['reason']
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
        need(row['payload'] == expected and row['label'] == label and row['mode'] == self.mode, 'REPLAY_REQUEST_DIFFERS')
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


def audit(folder):
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
    policy = json.loads((HERE/'policy.json').read_text())
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
    replay = Replay(folder, rows, policy, registered['run_started_ns'], journal[-1])
    cursor = 0
    def emit(kind, data):
        nonlocal cursor
        need(cursor < len(journal) and journal[cursor]['kind'] == kind and journal[cursor]['data'] == data, 'JOURNAL_REPLAY_DIFFERS')
        cursor += 1
    error = None
    try:
        run(replay, emit, policy, registered['registration_commit'], (folder/'source-registry.json').read_bytes())
    except Exception as caught:
        error = caught
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
    reads = [r['data'] for r in journal if r['kind'] == 'read_completed']
    return {'status': journal[-1]['kind'], 'rpc_calls': len(rows), 'http_requests': len(rows),
            'response_bytes': total, 'completed_triads': sum(r['kind'] == 'triad_completed' for r in journal),
            'reads': reads, 'cohort_accounts': len(registered['cohort']['addresses']),
            'source_registry_sha256': registered['cohort']['registry_sha256'],
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
    print(json.dumps({k: v for k, v in result.items() if k != 'reads'}))
