"""Finite, unsigned, loopback-only Anvil experiment; never connects to another node."""
import argparse
import hashlib
import json
import socket
import subprocess
import time
import urllib.request
from pathlib import Path
from Crypto.Hash import keccak

HERE=Path(__file__).resolve().parent
E=10**18
ZERO='0x'+'00'*20
MARKET='(address,address,address,address,uint256)'
PLAN='('+MARKET+',address,uint256,uint256,uint256,uint256,uint256,uint256,uint256,address,uint256)'
TRANSFER='0x'+keccak.new(digest_bits=256,data=b'Transfer(address,address,uint256)').hexdigest()

def digest(b): return hashlib.sha256(b).hexdigest()
def kh(b): return keccak.new(digest_bits=256,data=b).digest()
def word(v):
    n=int(v,16) if isinstance(v,str) else v
    if type(n) is not int or not 0<=n<2**256: raise ValueError('uint256 boundary')
    return n.to_bytes(32,'big')
def encode(args):
    # Static tuples are explicitly flattened; bytes are the only dynamic arguments used.
    head=[];tail=b'';size=32*len(args)
    for v in args:
        if isinstance(v,bytes):
            head.append(word(size+len(tail)))
            tail+=word(len(v))+v+b'\0'*((-len(v))%32)
        else: head.append(word(v))
    return b''.join(head)+tail
def calldata(sig,args=()): return '0x'+(kh(sig.encode())[:4]+encode(args)).hex()
def ints(raw):
    b=bytes.fromhex(raw[2:]);assert len(b)%32==0
    return [int.from_bytes(b[i:i+32],'big') for i in range(0,len(b),32)]
def addr(n): return '0x'+n.to_bytes(20,'big').hex()

class RPCError(Exception): pass

class Lab:
    def __init__(self,url,artifacts):
        self.url=url; self.art=artifacts; self.records=[];self.rejections=[];self.counter=0
        self.base_fee=10**9;self.priority=10**9;self.cap=3*10**9
        self.actors={k:addr(i+0x1001) for i,k in enumerate(('setup','sponsor_and_topup_financier','nqc_sender_and_beneficiary',
            'simulated_builder','proposer','lender','borrower','other_borrower','liquidity_provider'))}
        self.coinbase=self.actors['proposer'];self.asset={}
        self.http=urllib.request.build_opener(urllib.request.ProxyHandler({})) # Only our loopback child, not remote access.
    def rpc(self,m,p=None):
        self.counter+=1
        req=urllib.request.Request(self.url,json.dumps({'jsonrpc':'2.0','id':self.counter,'method':m,'params':p or []}).encode(),{'Content-Type':'application/json'})
        with self.http.open(req,timeout=20) as r: response=json.load(r)
        if 'error' in response: raise RPCError(response['error'])
        return response['result']
    def call(self,to,sig,args=()): return self.rpc('eth_call',[{'to':to,'data':calldata(sig,args)},'latest'])
    def token(self,token,account): return ints(self.call(token,'balanceOf(address)',[account]))[0]
    def balance(self,account): return int(self.rpc('eth_getBalance',[account,'latest']),16)
    def snapshot(self,addresses=None):
        return {a:{'ETH':self.balance(a),**{n:self.token(t,a) for n,t in self.asset.items()}}
                for a in sorted(set(addresses or self.actors.values()))}
    def tx(self,label,sender,to=None,data='0x',value=0,gas=2_500_000,expected=1,nonce=None,cap=None):
        self.rpc('anvil_setNextBlockBaseFeePerGas',[hex(self.base_fee)])
        self.rpc('evm_setNextBlockTimestamp',[1_800_000_000+int(self.rpc('eth_blockNumber'),16)+1])
        tx={'from':sender,'data':data,'value':hex(value),'gas':hex(gas),
            'maxFeePerGas':hex(self.cap if cap is None else cap),'maxPriorityFeePerGas':hex(self.priority)}
        if to:tx['to']=to
        tx['nonce']=hex(int(self.rpc('eth_getTransactionCount',[sender,'latest']),16) if nonce is None else nonce)
        before=self.snapshot()
        try: h=self.rpc('eth_sendUnsignedTransaction',[tx])
        except RPCError as exc:
            self.rejections.append({'label':label,'request':tx,'error':str(exc),'before':before,'after':self.snapshot(),'receipt':None})
            if expected=='REJECT':return None
            raise
        receipt=None
        for _ in range(100):
            receipt=self.rpc('eth_getTransactionReceipt',[h])
            if receipt is not None:break
            time.sleep(.02)
        if receipt is None: raise AssertionError('not mined; no claim of inclusion')
        trace=self.rpc('debug_traceTransaction',[h,{'tracer':'callTracer'}])
        block=self.rpc('eth_getBlockByHash',[receipt['blockHash'],False])
        if int(receipt['status'],16)!=expected:
            (HERE/'evidence/unexpected-failure.json').write_text(json.dumps({'label':label,'receipt':receipt,'trace':trace},indent=2)+'\n')
            raise AssertionError((label,receipt['status'],trace.get('error'),'see evidence/unexpected-failure.json'))
        if receipt['contractAddress']:
            new=receipt['contractAddress'].lower();self.actors[label]=new
            before[new]={'ETH':0,**{n:0 for n in self.asset}}
        after=self.snapshot()
        record={'label':label,'tx_index':len(self.records),'request':tx,'receipt':receipt,'trace':trace,
            'block':{k:block[k] for k in ('hash','parentHash','number','timestamp','baseFeePerGas','miner')},
            'before':before,'after':after,'gas_cost_wei':int(receipt['gasUsed'],16)*int(receipt['effectiveGasPrice'],16)}
        self.records.append(record)
        return record
    def deploy(self,name,sender,args=(),label=None,expected=1,value=0):
        r=self.tx(label or name,sender,data=self.art[name]['bytecode']+encode(args).hex(),value=value,
            gas=8_000_000 if name=='Morpho' else 4_000_000,expected=expected)
        return r['receipt']['contractAddress']
    def send(self,label,sender,to,sig,args=(),**kw): return self.tx(label,sender,to,calldata(sig,args),**kw)
    def setup(self):
        a=self.actors;s=a['setup']; lender=a['lender'];borrower=a['borrower'];other=a['other_borrower']
        assert int(self.rpc('eth_chainId'),16)==31337 and 'anvil' in self.rpc('web3_clientVersion').lower()
        assert self.rpc('eth_accounts')==[], 'No local keys/accounts are generated or used'
        self.rpc('anvil_setCoinbase',[self.coinbase])
        # Explicit synthetic allocation, never the operator. Each gas-consuming fixture actor is funded.
        allocations={s:2000*E,a['sponsor_and_topup_financier']:E,lender:E,borrower:E,other:E}
        for who,value in allocations.items():self.rpc('anvil_setBalance',[who,hex(value)])
        w=self.deploy('WETH',s);c=self.deploy('ERC20',s,[100000*E]);m=self.deploy('Morpho',s,[s]);o=self.deploy('LabOracle',s)
        factory=self.deploy('LabFactory',s);reject=self.deploy('RejectNative',s)
        self.asset={'WETH':w,'COLLATERAL':c}
        self.send('create_pair',s,factory,'create(bytes,address,address)',[bytes.fromhex(self.art['UniswapV2Pair']['bytecode'][2:]),c,w],gas=5_000_000)
        pair=addr(ints(self.call(factory,'pair()'))[0]);self.actors['dex_pair']=pair
        market=[w,c,o,ZERO,86*10**16];self.market=market;self.market_id='0x'+kh(encode(market)).hex()
        self.send('enable_zero_irm',s,m,'enableIrm(address)',[ZERO])
        self.send('enable_lltv',s,m,'enableLltv(uint256)',[market[-1]])
        self.send('create_market',s,m,f'createMarket({MARKET})',market)
        self.send('back_WETH',s,w,'deposit()',value=1002*E)
        self.send('lender_WETH',s,w,'transfer(address,uint256)',[lender,100*E])
        self.send('lender_approval',lender,w,'approve(address,uint256)',[m,100*E])
        self.send('supply',lender,m,f'supply({MARKET},uint256,uint256,address,bytes)',market+[100*E,0,lender,b''])
        for who,coll,debt,label in [(borrower,10*E,8*E,'target'),(other,200*E,92*E,'other')]:
            self.send(label+'_collateral',s,c,'transfer(address,uint256)',[who,coll])
            self.send(label+'_approval',who,c,'approve(address,uint256)',[m,coll])
            self.send(label+'_supply',who,m,f'supplyCollateral({MARKET},uint256,address,bytes)',market+[coll,who,b''])
            self.send(label+'_borrow',who,m,f'borrow({MARKET},uint256,uint256,address,address)',market+[debt,0,who,who])
        self.shares=ints(self.call(m,'position(bytes32,address)',[self.market_id,borrower]))[1]
        self.send('seed_pair_collateral',s,c,'transfer(address,uint256)',[pair,1000*E])
        self.send('seed_pair_WETH',s,w,'transfer(address,uint256)',[pair,900*E])
        self.send('mint_LP',s,pair,'mint(address)',[a['liquidity_provider']])
        self.send('oracle_synthetic_move',s,o,'setPrice(uint256)',[9*10**35])
        assert self.token(w,m)==0 and self.balance(a['nqc_sender_and_beneficiary'])==0
        self.setup_records=self.records;self.records=[]
        self.setup_report={'synthetic_allocations_wei':allocations,'owner_initial_assets':{'ETH':0,'WETH':0,'COLLATERAL':0},
            'market':market,'market_id':self.market_id,'shares':self.shares,'morpho_debt_cash':0,
            'oracle_initial':2*10**36,'oracle_liquidation':9*10**35,'pool_reserves':[1000*E,900*E],
            'zero_irm':'No interest accrual in this fixture; NOT historical interest reconstruction',
            'setup_gas_paid_by_external_fixture_actors':sum(r['gas_cost_wei'] for r in self.setup_records),
            'original_source_runtime_sha256':{n:digest(bytes.fromhex(self.rpc('eth_getCode',[a[n],'latest'])[2:]))
                for n in ('WETH','ERC20','Morpho','LabOracle','LabFactory','RejectNative','dex_pair')}}
    def state(self):
        return {'position':ints(self.call(self.actors['Morpho'],'position(bytes32,address)',[self.market_id,self.actors['borrower']])),
            'reserves':ints(self.call(self.actors['dex_pair'],'getReserves()')),
            'balances':self.snapshot()}
    def plan(self,changes=None):
        p={'borrower':self.actors['borrower'],'shares':self.shares,'expiry':100000,
           'min_out':811*10**16,'reserve':9*10**16,'min_weth':9*10**16,'min_profit':10**16,
           'tip':4*10**16,'sponsor':self.actors['sponsor_and_topup_financier'],'refund':5*10**16}
        p.update(changes or {})
        return self.market+list(p.values())+[b'\x01',b'']
    def scenario(self,name,mode='success',high_fee=False):
        a=self.actors;sponsor=a['sponsor_and_topup_financier'];operator=a['nqc_sender_and_beneficiary'];s=a['setup']
        self.records=[];self.rejections=[]
        self.base_fee=(20 if high_fee else 1)*10**9;self.priority=10**9;self.cap=(30 if high_fee else 3)*10**9
        self.rpc('anvil_setCoinbase',[a['proposer']]);self.coinbase=a['proposer']
        initial=self.state();advance=(3*10**17 if high_fee else 3*10**16)
        pchanges={};ex=None;approval_check=None;orphaned=[]
        if mode!='none':
            self.tx('topup',sponsor,operator,value=advance,gas=21000)
        if mode not in ('none','topup_only'):
            adapter=self.deploy('LabV2Adapter',operator,[a['dex_pair'],a['ERC20'],a['WETH']],label='nqc_adapter')
            bad=mode=='bad_create'
            ex=self.deploy('NqcMorphoSponsoredLiquidation',operator,[ZERO if bad else operator,a['Morpho'],adapter,a['WETH']],
                label='nqc_executor',expected=0 if bad else 1)
            if mode=='wrong_nonce':
                self.tx('stale_nonce',operator,sponsor,value=0,gas=21000,nonce=0,expected='REJECT')
            elif mode not in ('deploy_only','bad_create'):
                if mode in ('healthy','reorg'):
                    if mode=='reorg':
                        checkpoint=self.rpc('evm_snapshot');count=len(self.records)
                        self.send('orphaned_liquidation',operator,ex,f'execute({PLAN},bytes,bytes)',self.plan())
                        orphaned=self.records[count:];assert self.rpc('evm_revert',[checkpoint]);self.records=self.records[:count]
                    self.send('state_change_healthy',s,a['LabOracle'],'setPrice(uint256)',[2*10**36])
                if mode=='expired':pchanges['expiry']=0
                if mode=='slippage':pchanges['min_out']=8249365645570551239 # Exactly one wei above original AMM quote.
                if mode=='debt_shortfall':
                    self.send('competition_input',s,a['ERC20'],'transfer(address,uint256)',[a['dex_pair'],100*E])
                    self.send('competition_sync',s,a['dex_pair'],'sync()')
                    pchanges['min_out']=1
                if mode=='reject_sponsor':pchanges['sponsor']=a['RejectNative']
                if mode=='reject_proposer':
                    self.rpc('anvil_setCoinbase',[a['RejectNative']]);self.coinbase=a['RejectNative']
                if mode=='dust':
                    self.send('donated_old_WETH',s,a['WETH'],'transfer(address,uint256)',[ex,E])
                    self.send('donated_old_collateral',s,a['ERC20'],'transfer(address,uint256)',[ex,E])
                    self.deploy('ForceNative',s,[ex],label='force_native_donor',value=E)
                if mode=='overflow':pchanges['refund']=2**256-1
                if mode=='underallocated':pchanges['reserve']=9*10**16-1;pchanges['min_weth']=9*10**16-1
                if mode=='tip_too_large':pchanges.update(tip=2*10**17,reserve=25*10**16,min_weth=25*10**16)
                control=None
                if mode=='underpay_control':
                    control=self.deploy('UnderpayControl',operator,[a['Morpho'],a['ERC20'],a['WETH'],adapter],label='underpay_negative_control')
                pre_liquidation=self.state()
                failed=mode in ('healthy','reorg','expired','slippage','debt_shortfall','reject_sponsor','reject_proposer','wrong_sender','overflow','underallocated','tip_too_large','underpay_control')
                if control:
                    self.send('liquidate',operator,control,f'run({MARKET},address,uint256)',self.market+[a['borrower'],self.shares],expected=0)
                else:
                    self.send('liquidate',sponsor if mode=='wrong_sender' else operator,ex,f'execute({PLAN},bytes,bytes)',
                        self.plan(pchanges),expected=0 if failed else 1)
                after_liquidation=self.state()
                if failed:
                    assert after_liquidation['position']==pre_liquidation['position']
                    assert after_liquidation['reserves']==pre_liquidation['reserves']
                    for who,bb in pre_liquidation['balances'].items():
                        for token in self.asset:assert after_liquidation['balances'][who][token]==bb[token]
                else:
                    assert after_liquidation['position'][1]==0
                    assert self.token(a['WETH'],a['Morpho'])==8*E
                    assert self.token(a['WETH'],operator)==159365645570551238
                    assert self.balance(ex)==(E if mode=='dust' else 0)
                    assert self.token(a['WETH'],ex)==(E if mode=='dust' else 0)
                    assert self.token(a['ERC20'],ex)==(E if mode=='dust' else 0)
                approval_check={
                    'debt':ints(self.call(a['WETH'],'allowance(address,address)',[ex,a['Morpho']]))[0],
                    'collateral':ints(self.call(a['ERC20'],'allowance(address,address)',[ex,adapter]))[0]}
                assert approval_check=={'debt':0,'collateral':0}
                if not failed:
                    # A real local return transaction. Reserve is NOT counted as returned until this receipt succeeds.
                    actual_price=self.base_fee+self.priority
                    returned=self.balance(operator)-21000*actual_price
                    self.tx('return_unused_advance',operator,sponsor,value=returned,gas=21000,cap=actual_price)
                    self.tx('separate_builder_fee',sponsor,a['simulated_builder'],value=2*10**15,gas=21000)
                    assert self.balance(operator)==0
        final=self.state()
        cycle_completed=any(t['label']=='liquidate' and int(t['receipt']['status'],16)==1 for t in self.records)
        return {'scenario':name,'mode':mode,'chain_id':31337,'initial':initial,'final':final,'actors':dict(a),
            'synthetic_advance_wei':0 if mode=='none' else advance,'max_fee_per_gas_wei':self.cap,
            'base_fee_wei':self.base_fee,'priority_fee_wei':self.priority,'approval_check':approval_check,
            'transactions':self.records,'rpc_rejections':self.rejections,
            'orphaned_not_counted':orphaned,'external_costs':None,'real_failure_liability':None,
            'local_control_assertions_pass':True,
            'flags':{'EVM_LOCAL_PASS':cycle_completed if mode!='none' else None,'HISTORICAL_STATE_VERIFIED':None,'BUILDER_REAL_ACCEPTED':None,
                'NO_RECOURSE_FINANCING_VERIFIED':None,'COMPETITIVE_CAPTURE_VERIFIED':None,'REALIZED_NQC_PNL':None}}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--anvil',type=Path,required=True)
    p.add_argument('--only',default=None);a=p.parse_args()
    binary=a.anvil.resolve();version=subprocess.check_output([str(binary),'--version'],text=True).strip()
    if '1.7.1' not in version:raise ValueError('pinned Anvil 1.7.1 required')
    if digest(binary.read_bytes())!='10c1c727d6c1de973aeb160e59875b9a9a23464d6e74149ee8abb30b3500311b':
        raise ValueError('pinned Linux amd64 Anvil binary digest differs')
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    command=[str(binary),'--accounts','0','--host','127.0.0.1','--port',str(port),'--chain-id','31337',
        '--hardfork','cancun','--timestamp','1800000000','--base-fee','1000000000']
    process=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        lab=Lab(f'http://127.0.0.1:{port}',json.loads((HERE/'build/artifacts.json').read_text()))
        for _ in range(100):
            try:lab.rpc('web3_clientVersion');break
            except (OSError,RPCError):time.sleep(.05)
        else:raise RuntimeError('local Anvil did not start')
        lab.setup();base_actors=dict(lab.actors)
        (HERE/'evidence/setup.json').write_text(json.dumps({'report':lab.setup_report,'transactions':lab.setup_records},separators=(',',':'))+'\n')
        scenarios=[('C1_success','success',False),('C1_high_gas','success',True),('F01_none','none',False),
            ('F02_topup_only','topup_only',False),('F03_deploy_only','deploy_only',False),('F03_bad_create','bad_create',False),
            ('F04_healthy','healthy',False),('F05_one_wei_slippage','slippage',False),('F06_debt_shortfall','debt_shortfall',False),
            ('F06_one_wei_underpay','underpay_control',False),('F07_sponsor_reject','reject_sponsor',False),('F08_proposer_reject','reject_proposer',False),
            ('F09_nonce','wrong_nonce',False),('F10_expired','expired',False),('F10_reorg','reorg',False),
            ('F11_dust','dust',False),('F12_distinct_actors','success',False),('A_wrong_sender','wrong_sender',False),
            ('A_uint256_overflow','overflow',False),('A_one_wei_underfunded','underallocated',False),('A_tip_shortfall','tip_too_large',False)]
        index=[]
        for name,mode,high in scenarios:
            if a.only and name!=a.only:continue
            checkpoint=lab.rpc('evm_snapshot');lab.actors=dict(base_actors)
            result=lab.scenario(name,mode,high)
            raw=json.dumps(result,separators=(',',':'))+'\n';file=f'{name}.json'
            (HERE/'evidence'/file).write_text(raw)
            index.append({'scenario':name,'file':file,'sha256':digest(raw.encode()),'transactions':len(result['transactions']),
                'gas_used':sum(int(t['receipt']['gasUsed'],16) for t in result['transactions']),
                'classification':'LOCAL_SYNTHETIC_ASSERTIONS_PASS'})
            print(json.dumps(index[-1]),flush=True)
            assert lab.rpc('evm_revert',[checkpoint])
        (HERE/'evidence/run-index.json').write_text(json.dumps({'anvil_version':version,'anvil_sha256':digest(binary.read_bytes()),
            'unsigned_only':True,'private_keys_generated':0,'chain_id':31337,'hardfork':'cancun',
            'fork_url':None,'node_stopped_in_finally':True,'runs':index},indent=2)+'\n')
    finally:
        process.terminate()
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=10)

if __name__=='__main__':main()
