"""Recover a SYNTHETIC reserved NQC040 session from a fresh Git object store.

Uses read-only GitHub fetches, never Triport. The only transport is a spy that
must remain uncalled. This is an operational persistence probe, not live intake.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PREFIX = 'migration/experiments/nqc-046-durable-acquisition/'
REPOSITORY = 'https://github.com/josuechavando350-png/nexus-quant-capital.git'
sys.path.insert(0, str(HERE.parent / 'nqc-040-resumable-intake'))
import session as s


def recover(commit):
    s.t.v.require(re.fullmatch('[0-9a-f]{40}', commit), 'Exact commit required')
    calls = []
    with tempfile.TemporaryDirectory(prefix='nqc046-git-recovery-') as temporary:
        base = Path(temporary)
        repo, restored = base / 'git', base / 'synthetic-session'
        repo.mkdir()
        restored.mkdir()

        def git(*args):
            result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, check=True)
            return result.stdout

        git('init', '-q')
        # No local reference repository, alternates, or copied Git object cache.
        git('fetch', '--depth=1', REPOSITORY, commit)
        s.t.v.require(git('rev-parse', 'FETCH_HEAD').decode().strip() == commit, 'Wrong restored commit')
        meta = json.loads(git('show', commit + ':' + PREFIX + 'evidence/checkpoint/META.json'))
        s.t.v.require(meta == {'mode': 'DRY_RUN', 'rpc_requests_sent': 0,
                               'live_acquisition_session': False}, 'Probe context mismatch')
        raw = git('show', commit + ':' + PREFIX + 'evidence/checkpoint/SESSION.json')
        (restored / 'SESSION.json').write_bytes(raw)
        (restored / '.lock').touch(mode=0o600)
        # Original session.run verifies its full source/plan/input binding.
        def simulated_transport(operation):
            calls.append(operation['request']['id'])
            raise RuntimeError('Spy must never be called')
        report = s.run(restored, simulated_transport, secret='synthetic_probe_only', max_new_requests=8)
        s.t.v.require(report['status'] == 'BLOCKED_AMBIGUOUS_ATTEMPT', 'Restored reservation must block')
        s.t.v.require(not calls and report['attempt_slots_reserved'] == 1, 'Unexpected simulated dispatch')
        s.t.v.require(report['gates']['commercial_admission'] is False, 'Commercial gate opened')
        return {'evidence_class': 'real GitHub persistence/recovery; synthetic acquisition state',
                'recovered_commit': commit, 'new_git_object_directory': True,
                'local_git_object_cache_reused': False,
                'checkpoint_sha256': hashlib.sha256(raw).hexdigest(),
                'dry_run_session_result': report, 'simulated_transport_calls': len(calls),
                'triport_requests_sent': 0, 'historical_proofs_acquired': 0,
                'live_acquisition_session_created': False,
                'production_github_reservation_adapter_complete': False,
                'commercial_admission': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', required=True)
    args = parser.parse_args()
    result = recover(args.commit)
    (HERE / 'evidence/RECOVERY.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({k: result[k] for k in ('recovered_commit', 'simulated_transport_calls',
                                            'triport_requests_sent', 'commercial_admission')}))
