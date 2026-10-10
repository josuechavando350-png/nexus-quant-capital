"""Copy only closed captures after the exact published 139,000-block prefix."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import zipfile

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def canon(doc):
    return (json.dumps(doc, sort_keys=True, separators=(',', ':')) + '\n').encode()

live, base_path, out = map(Path, sys.argv[1:])
base_raw = base_path.read_bytes()
assert sha(base_raw) == '7b3310a04f198d2b3bd170b0d3d04e9621a25be0f6a88d8f5e5992402cfe5d26'
base = json.loads(base_raw)
assert base['new_blocks_verified'] == 139000 and base['closed_files_verified'] == 139
raw = (live / 'progress.json').read_bytes()
captured_at = datetime.now(timezone.utc).isoformat()
progress = json.loads(raw)
assert progress['producer_repository'] == 'josuechavando350-png/nexus-quant-capital'
assert progress['producer_commit'] == 'c163b876d3310855f1db45bfc3ab4189b24d865b'
assert progress['status'] == 'RUNNING' and progress['failure'] is None
assert progress['workers'] == 1 and progress['maximum_batch_size'] == 10
assert progress['minimum_request_interval_seconds'] >= 1.1
items = progress['completed_files']
assert items[:139] == base['closed_file_commitments'] and len(items) > 139
assert all(item['complete'] is True for item in items)
out.mkdir(parents=True, exist_ok=False)
(out / 'progress.json').write_bytes(raw)
(out / 'base-readback.json').write_bytes(base_raw)
(out / 'snapshot.py').write_bytes(Path(__file__).read_bytes())
for name in ['collect.py', 'resume.py', 'resume-plan.json', 'assets.json', 'anchors.jsonl.gz']:
    (out / name).write_bytes((live / name).read_bytes())
for item in items[139:]:
    assert item['file'] == f"capture-{item['plan_offset']:06d}.jsonl.gz"
    data = (live / item['file']).read_bytes()
    assert len(data) == item['bytes'] and sha(data) == item['sha256']
    (out / item['file']).write_bytes(data)
manifest = {'schema': 'nqc-closed-oracle-delta-006-v1',
    'base_evidence_commit': '91b7108c5b56c768127bd9b73202d5156635ec18',
    'base_readback_sha256': sha(base_raw), 'base_closed_files': 139,
    'base_blocks_verified': 139000, 'progress_snapshot_received_at': captured_at,
    'closed_files_in_snapshot': len(items), 'new_closed_files': len(items) - 139,
    'snapshot_source_sha256': sha(Path(__file__).read_bytes()),
    'capture_counter_is_not_verified_coverage': True,
    'new_requests_made_by_snapshot': 0, 'worker_modified': False,
    'members': [{'path': p.name, 'bytes': p.stat().st_size, 'sha256': sha(p.read_bytes())}
                for p in sorted(out.iterdir())]}
(out / 'manifest.json').write_bytes(canon(manifest))
archive = out.with_suffix('.zip')
with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for p in sorted(out.iterdir()):
        info = zipfile.ZipInfo(p.name, date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(info, p.read_bytes())
print(json.dumps({'archive': str(archive), 'bytes': archive.stat().st_size,
    'sha256': sha(archive.read_bytes()), 'members': len(list(out.iterdir())),
    'snapshot_at': captured_at, 'new_closed_files': len(items)-139,
    'all_closed_files': len(items), 'observed_counter': progress['observed_blocks']}, sort_keys=True))
