"""Emit reproducible outcome assessments for explicitly SYNTHETIC cases."""
import json
from pathlib import Path
from zero_swap_gate import evaluate
ROOT=Path(__file__).resolve().parent
cases=json.loads((ROOT/'fixtures.json').read_text(encoding='utf-8'))
result={"schema":"nqc061-offline-zero-swap-fixture-outcomes-v1",
        "all_fixtures_only":True,
        "real_candidates_authenticated":0,
        "results":{c['candidate_id']:evaluate(c) for c in sorted(cases,key=lambda x:x['candidate_id'])},
        "commercial_admission":False}
print(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False))
