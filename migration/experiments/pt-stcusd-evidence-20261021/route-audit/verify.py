"""Reproduce local data consistency checks only. No network or financial execution."""
import contextlib,io,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from route_audit import analyze
out=ROOT/'evidence';out.mkdir(exist_ok=True)
stream=io.StringIO()
suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'))
r=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
(out/'tests.log').write_text(stream.getvalue())
report={'tests':r.testsRun,'failures':len(r.failures),'errors':len(r.errors),'skipped':len(r.skipped),
 'network_calls':0,'evm_execution':False,'nqc_profit':None,'full_repository_suites':'NOT_RUN_NO_FULL_CHECKOUT'}
(out/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
if r.wasSuccessful():
 result=analyze(json.loads((ROOT/'inputs/route_evidence.json').read_text()),json.loads((ROOT/'reference/selected_log.json').read_text()))
 (out/'RESULT.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
print(json.dumps(report,indent=2))
sys.exit(0 if r.wasSuccessful() else 1)
