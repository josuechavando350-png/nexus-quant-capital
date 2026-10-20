"""Reproduce the exact missing-state boundary with preserved bytes and ZERO network."""
from pathlib import Path
import hashlib, json, os, subprocess, sys
from continue_original import HERE, PinnedHead, restore, rg, archive

class OfflineCache:
    def __init__(self,directory):
        self.directory=directory;directory.mkdir(parents=True,exist_ok=True)
        self.cache={};self.halted=None;self.used=0;self.missing=[];self.calls=0
        restore(self)
        source=HERE/'evidence/continuation_historical_metadata'
        for row in map(json.loads,(source/'network.jsonl').read_text().splitlines()):
            if row.get('http_status')!=200 or 'error' in row:continue
            raw=(source/row['body_path']).read_bytes()
            assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']
            response=json.loads(raw);q=row['request']
            assert response['id']==q['id'] and response.get('result') is not None and not response.get('error')
            key=json.dumps([q['method'],q['params']],sort_keys=True,separators=(',',':'))
            if key in self.cache:assert self.cache[key]==response['result']
            self.cache[key]=response['result']
    def call(self,method,params):
        self.calls+=1;rg.validate(method,params)
        key=json.dumps([method,params],sort_keys=True,separators=(',',':'))
        if key not in self.cache:
            self.missing.append({'method':method,'params':params})
            raise rg.Closed('OFFLINE_MISSING_EVIDENCE: '+key)
        return self.cache[key]

def run(tools):
    out=HERE/'evidence/offline_reproduction';out.mkdir(exist_ok=True)
    cache=OfflineCache(out);server=rg.serve(PinnedHead(cache))
    env=os.environ.copy();env.update(NQC_ARCHIVE_READ_APPROVED='true',NQC_ARCHIVE_RPC_URL='http://127.0.0.1:9855')
    args=[str(tools/'forge'),'test','--offline','--use',str(tools/'solc'),'--gas-price','302819782345','--match-contract','HistoricalFlashReplayTest','--match-test','^test_01_','-vvvv']
    try:
        p=subprocess.run(args,cwd=HERE/'runtime_source',env=env,capture_output=True,text=True,timeout=60)
        (out/'baseline.log').write_text(p.stdout+p.stderr)
    finally:server.shutdown();server.server_close()
    expected={'method':'eth_getStorageAt','params':['0x111111125421ca6dc452d289314280a0f8842a65','0x3','0x14c1350']}
    report={'network_requests':0,'preserved_successful_rpc_entries':len(cache.cache),'exit_code':p.returncode,
            'missing':cache.missing,'same_first_missing_read':bool(cache.missing and cache.missing[0]==expected),
            'baseline_passed':False,'variant_executed':False,'commercial_admission':False,'command':args}
    assert p.returncode!=0 and report['same_first_missing_read']
    (out/'RESULT.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':run(Path(sys.argv[1]).resolve())
