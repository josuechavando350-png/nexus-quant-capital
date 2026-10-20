"""One finite, cached, read-only historical RPC gate. No chain write is permitted."""
from __future__ import annotations
import hashlib, json, re, threading, time, urllib.request, urllib.error
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer

UPSTREAM = 'https://ethereum-rpc.publicnode.com'
PARENT = 21762896
TARGET = PARENT + 1
TX = '0x2a8880470bddca62a3b10586e1c65bd760c5a0d65da03d55cde94d0d709ed1eb'
PREFIX = '0x85f35a2fffc14c6a0b5744401b31ec3ff902f5981ff78d42af1a82f81c084595'
# The target block hash is independently read/validated by run_replay.py; not used as a state override.
ADDRESS = re.compile(r'0x[0-9a-fA-F]{40}\Z')
HEX32 = re.compile(r'0x[0-9a-fA-F]{64}\Z')
HEXNUM = re.compile(r'0x[0-9a-fA-F]+\Z')
MAX_READS = 1200
MAX_SECONDS = 600
MAX_BYTES = 8 * 1024 * 1024

class Closed(RuntimeError): pass

def height(value):
    if not isinstance(value,str) or not HEXNUM.fullmatch(value):
        raise Closed('Only explicit block numbers; latest/pending forbidden')
    return int(value,16)

def validate(method, p):
    if not isinstance(p,list): raise Closed('params must be list')
    if method == 'eth_chainId' and not p: return
    if method in ('eth_getTransactionByHash','eth_getTransactionReceipt') and len(p)==1 and p[0].lower() in (TX,PREFIX): return
    if method=='eth_getBlockByNumber' and len(p)==2 and type(p[1]) is bool:
        n=height(p[0])
        if TARGET-256<=n<=TARGET: return
    if method=='eth_getBlockByHash' and len(p)==2 and isinstance(p[0],str) and HEX32.fullmatch(p[0]) and type(p[1]) is bool: return
    if method in ('eth_getBalance','eth_getCode','eth_getTransactionCount') and len(p)==2:
        if isinstance(p[0],str) and ADDRESS.fullmatch(p[0]) and height(p[1])==PARENT: return
    if method=='eth_getStorageAt' and len(p)==3:
        if isinstance(p[0],str) and ADDRESS.fullmatch(p[0]) and isinstance(p[1],str) and HEXNUM.fullmatch(p[1]) and len(p[1])<=66 and height(p[2])==PARENT: return
    raise Closed('RPC not authorized: '+str(method))

class Guard:
    def __init__(self, directory:Path, opener=None, clock=time.monotonic, sleep=time.sleep):
        self.directory=directory; directory.mkdir(parents=True,exist_ok=True)
        self.opener=opener or urllib.request.urlopen
        self.clock=clock; self.sleep=sleep; self.started=clock(); self.last=0.0
        self.used=0; self.cache={}; self.halted=None; self.lock=threading.Lock()
    def call(self, method, params):
        with self.lock:
            validate(method,params)
            if self.halted: raise Closed('Halted: '+self.halted)
            key=json.dumps([method,params],sort_keys=True,separators=(',',':'))
            if key in self.cache: return self.cache[key]
            if self.used>=MAX_READS or self.clock()-self.started>MAX_SECONDS:
                self.halted='bounded request/time budget reached'; raise Closed(self.halted)
            self.sleep(max(0,0.35-(self.clock()-self.last)))
            self.used+=1; self.last=self.clock()
            req={'jsonrpc':'2.0','id':self.used,'method':method,'params':params}
            record={'request':req,'endpoint':UPSTREAM,'attempt':self.used}
            try:
                r=urllib.request.Request(UPSTREAM,data=json.dumps(req).encode(),method='POST',headers={'Content-Type':'application/json','User-Agent':'NQC-HistoricalReplay-ReadOnly/1.0'})
                with self.opener(r,timeout=20) as response:
                    record['http_status']=response.status
                    raw=response.read(MAX_BYTES+1)
                record['body_bytes']=len(raw); record['sha256']=hashlib.sha256(raw).hexdigest()
                if len(raw)>MAX_BYTES: raise Closed('Response size cap')
                record['raw_response_text']=raw.decode()
                if record['http_status']!=200: raise Closed('HTTP '+str(record['http_status']))
                result=json.loads(raw)
                if not isinstance(result,dict) or result.get('id')!=self.used or result.get('error') or 'result' not in result:
                    raise Closed('RPC envelope/error '+str(result)[:500])
                value=result['result']
                if value is None: raise Closed('Missing historical result: '+method)
                if method.startswith('eth_getBlock') and not TARGET-256<=height(value['number'])<=TARGET:
                    raise Closed('Block outside historical scope')
                self.cache[key]=value
                return value
            except Exception as exc:
                self.halted=type(exc).__name__+': '+str(exc)[:600]
                record['error']=self.halted
                raise Closed(self.halted) from exc
            finally:
                with (self.directory/'rpc_history.jsonl').open('a') as f: f.write(json.dumps(record,sort_keys=True)+'\n')
    def summary(self):
        return {'upstream_requests':self.used,'cache_entries':len(self.cache),'halted':self.halted,'upstream':UPSTREAM,'max_requests':MAX_READS,'read_only':True}

def serve(guard,port=9855):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            ident=None
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=100000: raise Closed('Request size')
                req=json.loads(self.rfile.read(length))
                if not isinstance(req,dict): raise Closed('Batch requests prohibited')
                ident=req.get('id')
                out={'jsonrpc':'2.0','id':ident,'result':guard.call(req['method'],req.get('params',[]))}
            except Exception as exc:
                out={'jsonrpc':'2.0','id':ident,'error':{'code':-32050,'message':str(exc)[:800]}}
            body=json.dumps(out).encode(); self.send_response(200)
            self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    server=HTTPServer(('127.0.0.1',port),Handler)
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    return server
