#!/usr/bin/env python3
"""Offline exact-output parity: Rust generic/fast, independent Python integers, pinned Solidity in local EVM.
Run using the isolated py-evm environment; no RPC, signing, transaction, funding or deployment.
"""
import argparse, gzip, hashlib, importlib.util, json, pathlib, random, subprocess, sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
MAX=2**256-1;MAX128=2**128-1;WAD=10**18;SCALE=10**36
class Panic(Exception):pass
def check(n):
    if not 0<=n<=MAX:raise Panic(17)
    return n
def md(x,y,d,up):
    n=check(x*y)
    if up:n=check(n+check(d-1))
    if d==0:raise Panic(18)
    return n//d
def assets(s,a,t,up):return md(s,check(a+1),check(t+1000000),up)
def taylor(r,t):
    f=check(r*t);s=md(f,f,2*WAD,False);th=md(s,f,3*WAD,False)
    return check(check(f+s)+th)
def model(op,a):
    try:
        if op=='D':v=[md(*a)]
        elif op=='A':v=[assets(*a)]
        elif op=='T':v=[taylor(*a)]
        elif op=='H':
            ta,ts,bs,coll,price,lltv=a;debt=assets(bs,ta,ts,True);cap=md(md(coll,price,SCALE,False),lltv,WAD,False);v=[debt,cap,int(debt>cap)]
        else:
            sa,ss,ba,bs,last,fee,now,kind,r=a
            if kind==0:return 'UNKNOWN'
            try:
                m=interest.MarketState(sa,ss,ba,bs,last,fee);p=interest.accrue(m,now,None if kind==1 else r)
                v=list(vars(p.market).values())+[p.interest,p.fee_shares]
            except ValueError:return 'UNKNOWN'
        return 'OK '+' '.join(f'{x:064x}' for x in v)
    except Panic as e:return f'ERR {e.args[0]}'
def rows():
    r=random.Random(666021);out=[]
    edge=[0,1,2,10**6-1,10**6,2**64-1,2**64,MAX128,2**128,2**255,MAX-1,MAX]
    for i in range(14000):
        width=r.choice([16,64,128,192,256]);x=r.getrandbits(width);y=r.getrandbits(r.choice([16,64,128,256]));d=r.choice(edge+[WAD,SCALE,r.getrandbits(256)])
        if i<400:x=edge[i%len(edge)];y=edge[(i//len(edge))%len(edge)]
        out.append(('D',[x,y,d,i%2]))
    for i in range(5000):
        a=[r.getrandbits(r.choice([16,64,128,256])) for _ in range(3)]+[i%2];out.append(('A',a))
    for i in range(3000):out.append(('T',[r.getrandbits(r.choice([24,40,128,256])),r.getrandbits(r.choice([16,32,64]))]))
    for i in range(6000):
        unit=r.choice([10**6,10**9,WAD,10**24]);ta=unit*r.randrange(1,100000);ts=min(MAX128,ta*10**6);bs=r.randrange(ts+1)
        out.append(('H',[ta,ts,bs,r.randrange(unit*100000),r.choice([SCALE,SCALE//100,100*SCALE,MAX]),r.randrange(WAD)]))
    for i in range(2000):
        sa=r.randrange(1,10**25);ba=r.randrange(sa);ss=sa*10**6;bs=ba*10**6;last=r.randrange(1,2**32);now=last+r.randrange(86401)
        out.append(('P',[sa,ss,ba,bs,last,r.choice([0,WAD//10,WAD//4,WAD]),now,i%3,r.choice([0,10**9,10**10,MAX])]))
    # Exact success and overflow boundaries, including an intermediate overflow despite a fitting mathematical quotient.
    out += [('D',[MAX,1,2,1]),('D',[0,0,0,1]),('D',[0,0,0,0]),('A',[1,MAX,1,0]),
      ('H',[99,99000000,1000000,2,SCALE,WAD//2]),('H',[99,99000000,1000001,2,SCALE,WAD//2])]
    return out
def evm_check(rows, expected, solc, out):
    from eth.chains.base import MiningChain
    from eth.db.atomic import AtomicDB
    from eth.vm.forks.paris import ParisVM
    from eth_hash.auto import keccak
    assert hashlib.sha256(solc.read_bytes()).hexdigest()=='7a5c1d3dc9a8eba62bb2ec37192c9178ae5fe8a54a56e5573fd3c9c17cd9eb48'
    sources={f.name:{'content':f.read_text()} for f in (ROOT/'reference').glob('*.sol')}
    inp={'language':'Solidity','sources':sources,'settings':{'optimizer':{'enabled':True,'runs':200},'evmVersion':'paris','outputSelection':{'FormulaHarness.sol':{'FormulaHarness':['abi','evm.deployedBytecode.object']}}}}
    build=json.loads(subprocess.check_output([str(solc),'--standard-json'],input=json.dumps(inp).encode()))
    assert not [e for e in build.get('errors',[]) if e['severity']=='error']
    (out/'solc-output.json').write_text(json.dumps(build,indent=2)+'\n')
    code=bytes.fromhex(build['contracts']['FormulaHarness.sol']['FormulaHarness']['evm']['deployedBytecode']['object'])
    Chain=MiningChain.configure(__name__='LocalFormulaChain',vm_configuration=((0,ParisVM),))
    vm=Chain.from_genesis(AtomicDB(),{'difficulty':0,'gas_limit':30000000,'timestamp':1}).get_vm()
    selector=keccak(b'evaluate(uint256,uint256[6])')[:4];addr=b'\x01'*20
    selected=[]
    for op in ['D','A','T','H']:
        ids=[i for i,v in enumerate(rows) if v[0]==op]
        # Includes every explicit boundary, with deterministic spread through random rows.
        selected.extend(ids[:32]+ids[-8:]+random.Random(666022).sample(ids,256))
    record=[]
    for i in sorted(set(selected)):
        op,a=rows[i];data=selector+b''.join(v.to_bytes(32,'big') for v in [['D','A','T','H'].index(op)]+a+[0]*(6-len(a)))
        c=vm.execute_bytecode(origin=addr,gas_price=0,gas=2000000,to=addr,sender=addr,value=0,data=data,code=code)
        if c.is_error:
            assert c.output[:4]==bytes.fromhex('4e487b71'),(i,c.output.hex(),str(c.error))
            actual=f'ERR {int.from_bytes(c.output[4:],"big")}'
        else:
            assert len(c.output)==96
            values=[int.from_bytes(c.output[j:j+32],'big') for j in range(0,96,32)]
            actual='OK '+' '.join(f'{v:064x}' for v in values[:3 if op=='H' else 1])
        assert actual==expected[i],(i,rows[i],actual,expected[i])
        record.append({'row':i,'op':op,'result':actual,'gas_used':c.get_gas_used()})
    (out/'evm-cases.json').write_text(json.dumps(record,indent=2)+'\n')
    return {'cases':len(record),'runtime_sha256':hashlib.sha256(code).hexdigest(),'scope':'LOCAL_PURE_FORMULAS_NOT_MORPHO_RUNTIME_OR_FORK'}
def main():
    p=argparse.ArgumentParser();p.add_argument('--eval',type=pathlib.Path,required=True);p.add_argument('--solc',type=pathlib.Path,required=True);p.add_argument('--out',type=pathlib.Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    global interest
    sys.path.insert(0,str(ROOT/'reference'));import morpho_interest_math as interest
    data=rows();lines=[' '.join([op]+[f'{x:064x}' for x in args]) for op,args in data];corpus=('\n'.join(lines)+'\n').encode();expected=[model(op,v) for op,v in data]
    for mode in [[],['--reference']]:
        actual=subprocess.check_output([str(a.eval.resolve()),*mode],input=corpus).decode().splitlines()
        assert len(actual)==len(expected)
        for i,(x,y) in enumerate(zip(actual,expected)):
            assert x==y,(i,data[i],x,y,mode)
    negatives=['','D','D 1 2 3 4','T +1 2','T -1 2','T xyz 1','T '+'f'*65+' 1','T 1 2 3','P 1 2 3','X 1']
    assert subprocess.check_output([str(a.eval.resolve())],input=('\n'.join(negatives)+'\n').encode()).decode().splitlines()==['PARSE_ERROR']*len(negatives)
    (a.out/'corpus.txt.gz').write_bytes(gzip.compress(corpus,mtime=0));outputs=('\n'.join(expected)+'\n').encode();(a.out/'outputs.txt.gz').write_bytes(gzip.compress(outputs,mtime=0))
    evm=evm_check(data,expected,a.solc,a.out)
    result={'scope':'SYNTHETIC_EXACT_FORMULA_PARITY','seed':666021,'cases':len(data),'by_op':{o:sum(x[0]==o for x in data) for o in ['D','A','T','H','P']},'parser_rejections':len(negatives),'fast_reference_python_equal':True,'corpus_sha256':hashlib.sha256(corpus).hexdigest(),'output_sha256':hashlib.sha256(outputs).hexdigest(),'evm':evm}
    (a.out/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
