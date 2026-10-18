"""Read-only audit of pinned NQC021 logs. Does not execute recovered code or EVM."""
import base64,gzip,hashlib,io,json,re,sys
from pathlib import Path,PurePosixPath

EXPECTED={'files':77,'gzip_sha256':'3ed88604eac3b379d65281dbe269c1b31b68c371c4bc210d7b9d9484888c867e','gzip_bytes':898082,'chunks':200}
SOURCE_SHA='7e4018d575084bc18f857a2466d1fde447f62d34'
RUN='39102577514'

def ensure(ok,message):
    if not ok:raise ValueError(message)
def digest(b):return hashlib.sha256(b).hexdigest()
def number(x):
    ensure(isinstance(x,str) and x.startswith('0x'),'expected hex quantity')
    y=int(x,16);ensure(0<=y<2**256,'invalid uint256');return y

def unpack(log):
    ensure(len(log.encode())<20_000_000,'log too large')
    metas=[];chunks={};ends=0;statuses=[]
    for line in log.splitlines():
        if 'NQC021_EXPORT_META ' in line:metas.append(json.loads(line.split('NQC021_EXPORT_META ',1)[1]))
        m=re.search(r'NQC021_CHUNK (\d{5}) ([A-Za-z0-9+/=]+)\s*$',line)
        if m:
            i=int(m[1]);ensure(i not in chunks,'duplicate chunk');chunks[i]=m[2]
        if line.rstrip().endswith('NQC021_EXPORT_END'):ends+=1
        if 'NQC021_STATUS ' in line:statuses.append(json.loads(line.split('NQC021_STATUS ',1)[1]))
    ensure(metas==[EXPECTED] and ends==1,'wrong source export metadata')
    ensure(set(chunks)==set(range(200)),'missing chunks')
    b=base64.b64decode(''.join(chunks[i] for i in range(200)),validate=True)
    ensure(len(b)==EXPECTED['gzip_bytes'] and digest(b)==EXPECTED['gzip_sha256'],'archive identity mismatch')
    with gzip.GzipFile(fileobj=io.BytesIO(b)) as z:decoded=z.read(64_000_001)
    ensure(len(decoded)<=64_000_000,'decompression limit')
    source=json.loads(decoded);ensure(isinstance(source,dict) and len(source)==77,'file count')
    files={};total=0
    for name,rec in source.items():
        ensure(name and not PurePosixPath(name).is_absolute() and not any(t in ('.','..') for t in name.split('/')) and not any(c in name for c in ('\\',':','\x00')),'unsafe path')
        raw=base64.b64decode(rec['base64'],validate=True);total+=len(raw)
        ensure(total<=40_000_000,'file byte limit')
        ensure(len(raw)==rec['bytes'] and digest(raw)==rec['sha256'],'file identity mismatch: '+name)
        files[name]=raw
    ensure(len(statuses)==1,'status count')
    st=statuses[0]
    ensure(st['producer_sha']==SOURCE_SHA and str(st['run_id'])==RUN,'wrong producer/run')
    ensure(st['new_evm_cases']==12 and st['final_receipts']==52,'source totals')
    return files,st

def unique_json(files,suffix):
    names=[n for n in files if n==suffix or n.endswith('/'+suffix)]
    ensure(len(names)==1,'unique evidence file missing: '+suffix)
    return json.loads(files[names[0]])

def audit_case(run,plan,summary):
    op=run['actors']['nqc_sender_and_beneficiary'].lower()
    builder=run['actors']['simulated_builder'].lower()
    initial={a.lower():v['ETH'] for a,v in run['initial']['balances'].items()}
    final={a.lower():v['ETH'] for a,v in run['final']['balances'].items()}
    ensure(initial[op]==0,'nonzero operator own ETH')
    net={};calls=0
    def add(a,v):net[a]=net.get(a,0)+v
    def walk(t):
        nonlocal calls
        if t.get('error'):return
        v=number(t.get('value','0x0'));kind=t.get('type','').upper()
        if v and kind in ('CALL','CREATE','CREATE2'):
            add(t['from'].lower(),-v);add(t['to'].lower(),v);calls+=1
        elif v:ensure(kind in ('STATICCALL','DELEGATECALL','CALLCODE'),'unsupported committed value trace')
        for child in t.get('calls',[]):walk(child)
    seen=set();blocks=set();indices=[];gas=0;requirements=[];op_labels=[];payout_before=None
    for tx in run['transactions']:
        req=tx['request'];receipt=tx['receipt'];block=tx['block'];h=receipt['transactionHash']
        ensure(h not in seen,'duplicate receipt');seen.add(h)
        blocks.add((receipt['blockHash'],receipt['blockNumber']))
        ensure(receipt['blockHash']==block['hash'] and receipt['blockNumber']==block['number'],'mixed block evidence')
        indices.append(number(receipt['transactionIndex']))
        g=number(receipt['gasUsed']);p=number(receipt['effectiveGasPrice']);base=number(block['baseFeePerGas'])
        sender=req['from'].lower();miner=block['miner'].lower()
        ensure(p>=base,'gas below base');gas+=g
        ensure(g<=number(req['gas']),'gas exceeds limit')
        ensure(number(req['maxFeePerGas'])>=p and number(req['maxFeePerGas'])>=number(req['maxPriorityFeePerGas']),'fee cap mismatch')
        add(sender,-g*p);add(miner,g*(p-base));add('BURN',g*base)
        status=number(receipt['status']);ensure(status in (0,1),'invalid status')
        if status==1:walk(tx['trace'])
        if sender==op:
            ensure(tx['label'] in ('nqc_adapter','nqc_executor','liquidate'),'unexpected operator instruction')
            reserve=number(req['value'])+number(req['gas'])*number(req['maxFeePerGas'])
            before=tx['before'][op]['ETH']
            ensure(before>=reserve,'included operator prefix lacks max-fee reserve')
            requirements.append(summary['provider_advance_wei']-before+reserve)
            op_labels.append((tx['label'],status))
        if tx['label']=='external_proposer_payout':
            ensure(sender==builder and miner==builder,'fixture payout identity changed')
            payout_before=tx['before'][builder]['ETH']-initial[builder]
    ensure(len(blocks)==1 and indices==list(range(len(indices))),'receipt index/block continuity')
    for a,start in initial.items():ensure(final[a]-start==net.get(a,0),'native balance mismatch: '+a)
    ensure(sum(net.values())==0,'native conservation')
    ensure(len(seen)==summary['receipt_count'] and gas==summary['gas_total'],'source count/gas mismatch')
    ensure(final[builder]-initial[builder]==summary['builder_cash_after_observed_payout'],'builder delta differs from source summary')
    ensure(final[op]==summary['residual_financing'],'operator residual mismatch')
    ensure(plan['revertingTxHashes']==[] and plan['droppingTxHashes']==[],'mandatory policy declaration changed')
    ensure(plan['signatures_created']==0 and plan['real_rpc_payload'] is False,'unexpected wire/signature claim')
    encoded=json.dumps(plan['operator_requests'],sort_keys=True,separators=(',',':')).encode()
    ensure(digest(encoded)==plan['operator_sha256']==summary['operator_sha256'],'operator request identity mismatch')
    core=op_labels==[('nqc_adapter',1),('nqc_executor',1),('liquidate',1)]
    return {'case':summary['case'],'receipts':len(seen),'native_transfers':calls,'gas':gas,
      'mandatory_operator_success_observed':core,
      'minimum_upfront_for_retained_prefixes_wei':max(requirements) if requirements else None,
      'minimum_scope':'ALL_THREE_RETAINED_PREFIXES' if len(op_labels)==3 else 'INCOMPLETE_PATH_NOT_FULL_MINIMUM',
      'builder_before_payout_observed_wei':payout_before,
      'builder_after_payout_wei':summary['builder_cash_after_observed_payout'],
      'residual_wei':summary['residual_financing'],
      'provider_admission':'NOT_TESTED','commercial_admission':False}

def main():
    files,st=unpack(Path(sys.argv[1]).read_text())
    result=[]
    for case in st['cases']:
        name=case['case']
        r=unique_json(files,name+'_execution.json');p=unique_json(files,name+'_plan.json')
        result.append(audit_case(r,p,case))
    report={'status':'RETAINED_RECEIPT_AUDIT_PASS_NOT_PROVIDER_ACCEPTANCE',
      'source_run':RUN,'source_sha':SOURCE_SHA,'archive_sha256':EXPECTED['gzip_sha256'],
      'source_files_verified':len(files),'receipts_audited':sum(r['receipts'] for r in result),
      'cases':result,'new_evm_executions':0,'public_transactions':0,'commercial_admission':False}
    ensure(report['receipts_audited']==52,'global receipt count')
    Path(sys.argv[2]).write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print('NQC023_AUDIT '+json.dumps(report,sort_keys=True))
if __name__=='__main__':main()
