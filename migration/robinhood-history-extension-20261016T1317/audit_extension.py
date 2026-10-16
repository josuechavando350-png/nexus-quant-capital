"""Offline PR19 replay with the new registered policy explicitly supplied."""
import argparse,json
from pathlib import Path
from continue_history import HERE,engine,replay

def audit(folder):
    return replay.audit(folder,json.loads((HERE/'policy.json').read_text()))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();result=audit(args.folder)
    args.out.write_bytes(engine.canonical(result))
    print(json.dumps({k:v for k,v in result.items() if k not in ('observations','cohort')}))
