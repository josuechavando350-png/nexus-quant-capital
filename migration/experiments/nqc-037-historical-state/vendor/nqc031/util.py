import hashlib
import json
from pathlib import Path
from Crypto.Hash import keccak

ROOT=Path(__file__).resolve().parents[1]
def require(ok,reason):
    if not ok:raise ValueError(reason)
def read(p):return json.loads(p.read_text())
def save(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n')
def sha(b):return hashlib.sha256(b).hexdigest()
def k256(b):return keccak.new(digest_bits=256,data=b).digest()
def unhex(x,size=None):
    require(isinstance(x,str) and x.startswith('0x') and len(x)%2==0,'invalid hex bytes')
    b=bytes.fromhex(x[2:])
    require(size is None or len(b)==size,'invalid byte width')
    return b
def quantity(x):
    require(isinstance(x,str) and x.startswith('0x') and len(x)>2,'invalid quantity')
    n=int(x,16);require(0<=n<2**256,'quantity outside uint256');return n

def check_remote():
    for row in read(ROOT/'REMOTE_INPUTS.json')['sources']:
        b=(ROOT/row['local_path']).read_bytes()
        require(sha(b)==row['sha256'],'source sha256 mismatch')
        require(hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==row['git_blob_sha'],'Git blob mismatch')
