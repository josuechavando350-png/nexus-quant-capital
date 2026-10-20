"""Pinned local fork adapter. No latest upstream, writes, retries or state overrides."""
from pathlib import Path
import datetime, hashlib, io, json, os, shutil, subprocess, sys, time, urllib.error, urllib.request

HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'runtime_source'
sys.path.insert(0, str(SOURCE))
import rpc_guard as rg
import archive_probe_replay as archive

def digest(b): return hashlib.sha256(b).hexdigest()
def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()

class PinnedHead:
    def __init__(self, guard): self.guard = guard
    def call(self, method, params):
        if method in ('eth_blockNumber','eth_gasPrice') and params == []:
            if self.guard.halted: raise rg.Closed('Halted: '+self.guard.halted)
            key = json.dumps(['eth_getBlockByNumber',[hex(rg.TARGET),False]],sort_keys=True,separators=(',',':'))
            block = self.guard.cache[key]
            if block['hash'] != archive.TARGET_HASH: raise rg.Closed('Pinned head conflict')
            value=block['number']
            origin='LOCAL_DERIVED_FROM_PRESERVED_TARGET_HEADER'
            if method=='eth_gasPrice':
                receipt_key=json.dumps(['eth_getTransactionReceipt',[rg.TX]],sort_keys=True,separators=(',',':'))
                receipt=self.guard.cache[receipt_key]
                if receipt['blockHash']!=archive.TARGET_HASH:raise rg.Closed('Receipt context conflict')
                value=receipt['effectiveGasPrice']
                origin='LOCAL_HISTORICAL_GAS_SETTING_FROM_PRESERVED_RECEIPT_NOT_CURRENT_QUOTE'
            with (self.guard.directory/'local_adapter.jsonl').open('a') as f:
                f.write(json.dumps({'timestamp_utc':now(),'method':method,'params':params,'result':value,
                    'origin':origin,'upstream_request':False})+'\n')
            return value
        # Pure canonicalization prevents repeated reads of identical addresses/slots.
        params = [x.lower() if isinstance(x,str) and x.startswith('0x') else x for x in params]
        return self.guard.call(method, params)

def restore(guard):
    prior = HERE/'evidence/prior_run'
    rows = [json.loads(s) for s in (prior/'rpc_history.jsonl').read_text().splitlines()]
    probe = json.loads((HERE/'evidence/capability_balance_probe.json').read_text())
    raw = (HERE/'evidence'/probe['body_path']).read_bytes()
    rows.append({'request':probe['request'],'sha256':probe['sha256'],'body_bytes':probe['bytes'],'raw_response_text':raw.decode()})
    total = 0
    for row in rows:
        raw = row['raw_response_text'].encode()
        if digest(raw)!=row['sha256'] or len(raw)!=row['body_bytes']: raise rg.Closed('Recovered body mismatch')
        response=json.loads(raw); q=row['request']
        if response.get('id')!=q['id'] or response.get('error') or response.get('result') is None: raise rg.Closed('Invalid recovered response')
        rg.validate(q['method'],q['params'])
        key=json.dumps([q['method'],q['params']],sort_keys=True,separators=(',',':'))
        if key in guard.cache: raise rg.Closed('Duplicate restored request')
        guard.cache[key]=response['result'];total+=len(raw)
    if len(rows)!=10: raise rg.Closed('Wrong prior request count')
    guard.used=10
    return total

def run(out, tools, runtime):
    archive.configure_transport()
    out.mkdir(parents=True,exist_ok=True)
    guard=rg.Guard(out)
    total_bytes=restore(guard)
    opener=urllib.request.build_opener(archive.NoRedirect())
    def recorded_open(request,timeout):
        nonlocal total_bytes
        if request.full_url!=archive.ENDPOINT: raise rg.Closed('Wrong endpoint')
        record={'timestamp_utc':now(),'request':json.loads(request.data),'endpoint':request.full_url}
        started=time.monotonic()
        try:
            try:
                with opener.open(request,timeout=timeout) as r:
                    record['http_status']=r.status;raw=r.read(rg.MAX_BYTES+1)
            except urllib.error.HTTPError as e:
                record['http_status']=e.code;raw=e.read(rg.MAX_BYTES+1)
            record['bytes']=len(raw);record['sha256']=digest(raw)
            name='response_'+str(record['request']['id'])+'.bin'
            (out/name).write_bytes(raw);record['body_path']=name
            total_bytes+=len(raw)
            if len(raw)>rg.MAX_BYTES or total_bytes>16*1024*1024:raise rg.Closed('Response budget')
            if record['http_status']!=200:raise rg.Closed('HTTP '+str(record['http_status']))
            value=io.BytesIO(raw);value.status=record['http_status'];return value
        except Exception as e:
            record['error']=type(e).__name__+': '+str(e);raise
        finally:
            record['duration_seconds']=time.monotonic()-started
            with (out/'network.jsonl').open('a') as f:f.write(json.dumps(record,sort_keys=True)+'\n')
    guard.opener=recorded_open
    adapter=PinnedHead(guard)
    result={'started_utc':now(),'stage':'baseline_only','baseline_replayed':False,'variant_executed':False,
            'prior_drpc_reads':10,'new_rpc_reads':0,'commercial_admission':False,'sponsor_accepted':False}
    server=None
    try:
        result['preflight']=archive.preflight(adapter)
        server=rg.serve(adapter)
        env=os.environ.copy();env.update(NQC_ARCHIVE_READ_APPROVED='true',NQC_ARCHIVE_RPC_URL='http://127.0.0.1:9855')
        receipt=adapter.call('eth_getTransactionReceipt',[rg.TX])
        # A concrete historical CLI price avoids a current eth_gasPrice read.
        # vm.transact still uses the historical transaction envelope.
        price=int(receipt['effectiveGasPrice'],16)
        if price!=302819782345:raise rg.Closed('Historical price conflict')
        args=[str(tools/'forge'),'test','--offline','--use',str(tools/'solc'),'--gas-price',str(price),'--match-contract','HistoricalFlashReplayTest','--match-test','^test_01_','-vvvv']
        started=time.monotonic()
        p=subprocess.run(args,cwd=runtime,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=440)
        (out/'baseline.log').write_text(p.stdout)
        result.update(command=args,exit_code=p.returncode,duration_seconds=time.monotonic()-started,baseline_replayed=p.returncode==0)
        print(p.stdout,flush=True)
    except Exception as e: result['error']=type(e).__name__+': '+str(e)
    finally:
        if server:server.shutdown();server.server_close()
        result.update(rpc=guard.summary(),new_rpc_reads=guard.used-10,total_response_bytes=total_bytes,finished_utc=now())
        (out/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)
    return 0 if result['baseline_replayed'] else 2

if __name__=='__main__':
    if len(sys.argv)!=4:raise SystemExit('Usage: continue_original.py OUTPUT TOOLS RUNTIME')
    raise SystemExit(run(Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve(),Path(sys.argv[3]).resolve()))
