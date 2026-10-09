"""Forge only local synthetic packages, updating outer SHA inventories."""
import json, sys, tempfile
from pathlib import Path
IMPL=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).parent/'baseline'
sys.path.insert(0,str(IMPL)); sys.dont_write_bytecode=True
from temporal_common import canonical, decode, sha
from synthetic_fixture import make
import build_temporal_package as builder
import verify_temporal_package as verifier

def change_json(pkg,file,fn):
    p=pkg/file; d=decode(p.read_bytes()); fn(d); p.write_bytes(canonical(d))
def rehash(pkg):
    p=pkg/'manifest.json'; m=decode(p.read_bytes())
    m['source_sha256']=sha((pkg/'raw-source.json').read_bytes())
    for rel in m['files']:
        b=(pkg/rel).read_bytes(); m['files'][rel]={'sha256':sha(b),'bytes':len(b)}
    p.write_bytes(canonical(m))

PROBES=[
 ('report_boolean_episode_count','report.json',lambda d:d.update(episode_count=True)),
 ('report_boolean_unknown_count','report.json',lambda d:d.update(material_unknown_count=False)),
 ('report_integer_coverage_flag','report.json',lambda d:d.update(coverage_complete_for_supplied_scope=1)),
 ('report_integer_authority','report.json',lambda d:d.update(terminal_authority=0)),
 ('episode_float_lifetime','episodes.jsonl',lambda d:d.update(lifetime_seconds=24.0)),
 ('episode_integer_censoring','episodes.jsonl',lambda d:d.update(left_censored=0)),
 ('episode_float_block','episodes.jsonl',lambda d:d['birth'].update(block=101.0)),
 ('source_unsafe_original_evidence_path','raw-source.json',lambda d:d['evidence'][0].update(path='../../escape')),
 ('source_unknown_inventory_field','raw-source.json',lambda d:d['evidence'][0].update(unreviewed_extra=True)),
 ('source_duplicate_original_paths','raw-source.json',lambda d:d['evidence'][0].update(path=d['evidence'][1]['path'])),
]

results=[]
for name,file,fn in PROBES:
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp); src=make(root/'src'); pkg=root/'pkg'
        builder.build(src,src.parent,pkg); change_json(pkg,file,fn); rehash(pkg)
        try: results.append({'probe':name,'outcome':'ACCEPTED','verifier':verifier.verify(pkg)})
        except Exception as e: results.append({'probe':name,'outcome':'REJECTED','error':str(e),'type':type(e).__name__})
print(json.dumps({'implementation':str(IMPL),'results':results},indent=2))
if '--require-fail-closed' in sys.argv:
    assert all(r['outcome']=='REJECTED' and r['type']=='Invalid' for r in results), 'Rehashed package forgery remains accepted; inspect results.'
