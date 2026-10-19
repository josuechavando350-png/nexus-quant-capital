"""NQC051: read-only, source-byte-pinned extraction of actual NQC037 prefix functions.

This is not the complete NQC037 account/storage proof verifier. ONLY chain and
parent header are allowed; no third step, RPC, network, credentials or writes.
"""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

VERIFY_SHA='a417a48eaf4dbabc36ded493730e6ce97cecb4e8'
INTAKE_SHA='c36d60ce83e73d246496bd0b72bc6cbe00d5893e'
PARENT_INPUT_SHA='d8576f0e73000d4ab993d69134ff0713ef70ca16'
EXTRACT_HASHES={
 'ValidationError':'70aadbc524bde817a69f1feb58ed37554db426a9ff29c160c2c1512c8bf61371',
 'require':'a3ea748e78642fdd1324e90f041b4d5f3573225c3bf475c5015013fb7c84d25a',
 'k256':'26a794fb69a00431963e610f4ecbca5eccd1339eedde2b891fb5f5141b5a43ca',
 'data_hex':'57ac85be00e4d7ae88855c80e3c2b88ffe75808056f2409a99b96ac707e19007',
 'quantity':'0c10977878e26e958737c2f881e156220a1052ee4c3794a5e6de6a397bbcb482',
 'validate_header':'c8a1b6b91800b298fb32e104512744836ca691da850beeb5265a5e41051bf0d7',
 'envelope':'fb017e5cbfb98f5e67960713fadb67732c6c8ad174be6b5a3d13e5dc7521fe13',
 'validate_step':'b2816065aa20411f9b954cbe639b66c3e0f47cf874fa4ead4946a82f6b3163ac',
}

class UnsafeEvidence(ValueError): pass

def need(ok,code):
    if not ok: raise UnsafeEvidence(code)

def sha(x): return hashlib.sha256(x).hexdigest()

def git_sha(b):return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()

def read_pinned(path,expected):
    p=Path(path)
    need(p.is_file() and not p.is_symlink(),'MISSING_PINNED_SOURCE')
    b=p.read_bytes()
    need(len(b)<=16*1024*1024 and git_sha(b)==expected,'PINNED_SOURCE_CHANGED')
    return b.decode('utf-8')

def excerpts(source,names):
    t=ast.parse(source)
    funcs={}
    for n in t.body:
        if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names:
            s=ast.get_source_segment(source,n)
            need(s is not None and sha(s.encode('utf-8'))==EXTRACT_HASHES[n.name],
                 'ORIGINAL_FUNCTION_HASH_CHANGED')
            funcs[n.name]=s
    need(set(funcs)==set(names),'ORIGINAL_FUNCTION_MISSING')
    return funcs

def compile_original_prefix(v_source,i_source,rlp,keccak):
    v_names=['ValidationError','require','k256','data_hex','quantity','validate_header']
    i_names=['envelope','validate_step']
    pieces=excerpts(v_source,v_names)
    pieces.update(excerpts(i_source,i_names))
    env={
        're':re, 'rlp':rlp, 'keccak':keccak,
        'CHAIN_ID':4663,'PARENT_NUMBER':66744161,
        'PARENT_HASH':'0x53f9d3bedcdd3554f7447343ca03f9c9a5a7b61c692057f431d9225e04e1a917',
        'PARENT_ROOT':'0xc07bf301da73475b44460226757ddfd1c2ee60a6d7346e3749de6953f78bae4a',
    }
    for name in [*v_names,*i_names]:
        exec(compile(pieces[name],f'<NQC037_VERBATIM_{name}>','exec'),env)
    def verify_two(operation,response,state):
        need(operation.get('purpose') in ('chain','parent') and
             operation.get('request',{}).get('id')==(['chain','parent'].index(operation['purpose'])+1),
             'THIRD_OR_DIFFERENT_STEP_DISABLED')
        return env['validate_step'](operation,response,state)
    return env,verify_two

def audit_checkout(repo_root):
    base=Path(repo_root)/'migration'/'experiments'
    v=read_pinned(base/'nqc-037-historical-state/src/verify.py',VERIFY_SHA)
    i=read_pinned(base/'nqc-037-historical-state/src/intake.py',INTAKE_SHA)
    p=read_pinned(base/'nqc-037-historical-state/inputs/parent-header.json',PARENT_INPUT_SHA)
    overlay=base/'nqc-050-openssl-crypto-overlay/compat'
    need((overlay/'rlp.py').is_file(),'OVERLAY_UNAVAILABLE')
    sys.path.insert(0,str(overlay))
    try:
        import rlp
        from Crypto.Hash import keccak
        need(Path(rlp.__file__).resolve()==(overlay/'rlp.py').resolve(),'FOREIGN_RLP')
        need(Path(keccak.__file__).resolve()==(overlay/'Crypto/Hash/keccak.py').resolve(),'FOREIGN_KECCAK')
        env,verify_two=compile_original_prefix(v,i,rlp,keccak)
        # Original header observation was captured with id=6, not plan request id=2.
        raw=json.loads(p)
        need(raw.get('id')==6 and raw.get('jsonrpc')=='2.0','CAPTURE_ORIGIN_CHANGED')
        header=raw['result'];actual=env['validate_header'](header,env['PARENT_HASH'],env['PARENT_NUMBER'])
        need(header['stateRoot']==env['PARENT_ROOT'],'CAPTURED_ROOT_CHANGED')
        try:verify_two({'purpose':'parent','request':{'id':2}},raw,{})
        except env['ValidationError']:
            rejected_original_envelope=True
        else:
            rejected_original_envelope=False
        need(rejected_original_envelope,'WRONG_ID_WAS_ACCEPTED')
        return {'status':'CAPTURED_HEADER_VERIFIED_PROVIDER_UNAUTHENTICATED',
          'sha_parent_header':actual, 'captured_rpc_id':6,'authorized_plan_id':2,
          'raw_saved_envelope_rejected':True,'read_only':True,
          'triport_authenticated_requests':0,'historical_state_proofs_acquired':0,
          'commercial_admission':False}
    finally:
        sys.path.remove(str(overlay))

if __name__=='__main__':
    import argparse
    arg=argparse.ArgumentParser();arg.add_argument('--repo-root',type=Path,required=True)
    a=arg.parse_args()
    try: result=audit_checkout(a.repo_root)
    except Exception:
        result={'status':'BLOCKED_PIN_OR_DEPENDENCY', 'commercial_admission':False,
          'historical_state_proofs_acquired':0, 'triport_authenticated_requests':0}
    print(json.dumps(result,sort_keys=True))
    if result['status']!='CAPTURED_HEADER_VERIFIED_PROVIDER_UNAUTHENTICATED':raise SystemExit(2)
