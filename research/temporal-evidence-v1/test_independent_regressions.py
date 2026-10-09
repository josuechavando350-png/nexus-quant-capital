"""Permanent independent review reproductions, run without external services."""
import json, os, subprocess, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent

class IndependentReviewRegressions(unittest.TestCase):
    def run_probe(self,name,expected):
        p=subprocess.run([sys.executable,str(ROOT/'regression_cases'/name),str(ROOT),'--require-fail-closed'],
                         capture_output=True,text=True,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
        self.assertEqual(p.returncode,0,p.stderr+'\n'+p.stdout)
        report=json.loads(p.stdout); self.assertEqual(len(report['results']),expected)
        self.assertTrue(all(r['outcome']!='ACCEPTED' for r in report['results']))
    def test_all_independent_source_negatives(self): self.run_probe('source_negatives.py',29)
    def test_all_rehashed_output_forgeries(self): self.run_probe('output_forgeries.py',10)

if __name__=='__main__': unittest.main()
