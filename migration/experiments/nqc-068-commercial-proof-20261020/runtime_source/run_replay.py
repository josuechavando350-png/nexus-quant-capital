"""Compile then reproduce the real original and zero-principal variant, no broadcast."""
from pathlib import Path
import hashlib, json, os, subprocess, sys, tarfile, time, urllib.request
from rpc_guard import Guard, serve, TX, PREFIX, TARGET, PARENT
HERE=Path(__file__).resolve().parent
OUT=HERE/'evidence_run';OUT.mkdir(exist_ok=True)
BIN=HERE/'tools';BIN.mkdir(exist_ok=True)
FOUNDRY_URL='https://github.com/foundry-rs/foundry/releases/download/v1.3.1/foundry_v1.3.1_linux_amd64.tar.gz'
FOUNDRY_SHA='baad3e1b06d6f310d210c93e95258a03d923fe610f8d0742138f2245f94abd7c'
SOLC_URL='https://binaries.soliditylang.org/linux-amd64/solc-linux-amd64-v0.8.26+commit.8a97fa7a'
SOLC_SHA='d5f23436f443edb85d8e76906d12f0a86ce0490e7663a9e608efeb7a93f149ef'
PARENT_HASH='0xc3b1f4fe26e6743df8727eceec10c536b33db580b3346fa87e731d888ca5f4d3'
TARGET_HASH='0x2702da91c548f69a98373525ae8409c6bd28189439bb53f2acb971a029ac5882'
result={'schema':'nqc-isolated-evm-replay-run-v1','compiled':False,'baseline_replayed':False,'variant_tested':False,'all_variant_tests_pass':False,'complete_receipt_cost':None,'realized_NQC_profit':None,'sponsor_accepted':False,'commercial_admission':False,'producer_sha':os.environ.get('GITHUB_SHA')}

def download(url,path,digest,maxbytes):
    req=urllib.request.Request(url,headers={'User-Agent':'NQC-Isolated-Research/1.0'})
    with urllib.request.urlopen(req,timeout=60) as r:
        if r.status!=200: raise RuntimeError('Tool download HTTP '+str(r.status))
        raw=r.read(maxbytes+1)
    if len(raw)>maxbytes or hashlib.sha256(raw).hexdigest()!=digest: raise RuntimeError('Tool size/hash mismatch '+path.name)
    path.write_bytes(raw); print('TOOL_VERIFIED',path.name,len(raw),digest,flush=True)

def command(args,label,timeout=300):
    print('STAGE',label,flush=True)
    p=subprocess.run(args,cwd=HERE,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout,env=os.environ.copy())
    text=p.stdout
    (OUT/(label+'.log')).write_text(text)
    print(text,flush=True)
    result[label+'_returncode']=p.returncode
    if p.returncode: raise RuntimeError(label+' failed')
    return text

def main():
    guard=None;server=None
    try:
        subprocess.run([sys.executable,'-m','unittest','-v','test_guard'],cwd=HERE,check=True)
        download(FOUNDRY_URL,BIN/'foundry.tar.gz',FOUNDRY_SHA,80000000)
        with tarfile.open(BIN/'foundry.tar.gz') as t:
            for name in ['forge','cast','anvil']:
                member=t.getmember(name)
                if not member.isfile():raise RuntimeError('Bad binary member')
                (BIN/name).write_bytes(t.extractfile(member).read());(BIN/name).chmod(0o755)
        download(SOLC_URL,BIN/'solc',SOLC_SHA,20000000);(BIN/'solc').chmod(0o755)
        command([str(BIN/'forge'),'--version'],'forge_version')
        command([str(BIN/'solc'),'--version'],'solc_version')
        command([str(BIN/'forge'),'build','--offline','--use',str(BIN/'solc')],'compile')
        result['compiled']=True
        guard=Guard(OUT)
        if guard.call('eth_chainId',[])!='0x1':raise RuntimeError('Wrong chain')
        parent=guard.call('eth_getBlockByNumber',[hex(PARENT),False])
        block=guard.call('eth_getBlockByNumber',[hex(TARGET),False])
        checks={'parent_hash':parent['hash'].lower()==PARENT_HASH,'target_hash':block['hash'].lower()==TARGET_HASH,'parent_link':block['parentHash'].lower()==PARENT_HASH,'height':int(block['number'],16)==TARGET,'timestamp':int(block['timestamp'],16)==1738548455,'base_fee':int(block['baseFeePerGas'],16)==302819782345,'prefix':block['transactions'][0].lower()==PREFIX,'target_index':block['transactions'][1].lower()==TX,'count':len(block['transactions'])==41}
        result['anchor_checks']=checks
        (OUT/'block_anchor.json').write_text(json.dumps({'parent':parent,'target':block},indent=2))
        print('ANCHOR_CHECKS '+json.dumps(checks),flush=True)
        if not all(checks.values()):raise RuntimeError('Historical anchor conflict; no substitutes')
        receipt=guard.call('eth_getTransactionReceipt',[TX])
        tx=guard.call('eth_getTransactionByHash',[TX])
        result['receipt_identity']={'tx':receipt['transactionHash'],'status':receipt['status'],'gas_used':int(receipt['gasUsed'],16),'gas_price':int(receipt['effectiveGasPrice'],16),'log_count':len(receipt['logs']),'input_bytes':(len(tx['input'])-2)//2}
        print('ORIGINAL_RECEIPT '+json.dumps(result['receipt_identity']),flush=True)
        if receipt['transactionHash'].lower()!=TX or receipt['blockHash'].lower()!=TARGET_HASH or receipt['status']!='0x1':raise RuntimeError('Receipt identity')
        if int(receipt['gasUsed'],16)!=602029 or int(receipt['effectiveGasPrice'],16)!=302819782345:raise RuntimeError('Original receipt differs; investigate before accepting')
        server=serve(guard)
        os.environ['NQC_ARCHIVE_READ_APPROVED']='true';os.environ['NQC_ARCHIVE_RPC_URL']='http://127.0.0.1:9855'
        base=[str(BIN/'forge'),'test','--offline','--use',str(BIN/'solc'),'--match-contract','HistoricalFlashReplayTest']
        command(base+['--match-test','^test_01_','-vvv'],'baseline',500)
        result['baseline_replayed']=True
        result['variant_tested']=True
        command(base+['--match-test','^test_0[234]_','-vvvv'],'variant',500)
        result['all_variant_tests_pass']=True
        result['verdict']='EVM_TOKEN_PATH_PASS_NOT_SPONSORSHIP_OR_REALIZED_PROFIT'
    except Exception as exc:
        result['error']=type(exc).__name__+': '+str(exc)
        result['verdict']='BLOCKED_OR_FAILED_NOT_ECONOMIC_APPROVAL'
        print('STOP '+result['error'],flush=True)
    finally:
        if server:server.shutdown();server.server_close()
        if guard:result['rpc']=guard.summary()
        files={p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in OUT.iterdir() if p.is_file()}
        result['evidence_files']=files
        (OUT/'RESULT.json').write_text(json.dumps(result,indent=2))
        print('NQC_RESULT '+json.dumps(result,sort_keys=True),flush=True)
    return 0 if result['all_variant_tests_pass'] else 2
if __name__=='__main__':raise SystemExit(main())
