/* Reproduce the committed NQC052 remote-recovery result offline. No writes/RPC. */
"use strict";
const fs=require("node:fs"),path=require("node:path"),{execFileSync,spawnSync}=require("node:child_process");
const bridge=require("./authentic_bridge.js"),adapter=require("./github_store.js");
const ledger=require("../nqc-048-durable-chunked-receipts/chunked_ledger.js");
const hash=require("../nqc-047-remote-ledger/ledger_engine.js").sha256;
const repo=path.resolve(__dirname,"../../.."),commit=process.argv[2];
if(!/^[0-9a-f]{40}$/.test(commit||""))throw Error("Exact 40-character commit required");
function git(...args){return execFileSync("git",["-C",repo,...args],{encoding:"utf8",maxBuffer:1024*1024});}
function fileAt(tip,p){
 if(tip!==commit)throw Error("Snapshot changed");
 return {sha:git("rev-parse",tip+":"+p).trim(),content:git("show",tip+":"+p)};
}
const store={head:async()=>commit,at:async tip=>fileAt(tip,adapter.JOURNAL),
 readPart:async(tip,id,index)=>fileAt(tip,adapter.chunkPath(id,index)),
 put:async()=>{throw Error("READ_ONLY");},writePart:async()=>{throw Error("READ_ONLY");}};
const read=p=>JSON.parse(fs.readFileSync(path.join(repo,"migration/experiments",p)));
async function runPython(raw){
 const p=spawnSync(process.env.NQC052_PYTHON||"python",["-I",path.join(__dirname,"worker.py"),"--repo-root",repo],
  {input:raw,encoding:"utf8",maxBuffer:1024*1024,timeout:20000});
 if(![0,2].includes(p.status)||p.stderr)throw Error("WORKER_UNAVAILABLE");return JSON.parse(p.stdout);
}
const engine=bridge.create({ledger,hash,store,runPython,spec:read("nqc-038-archive-access/TRIPORT_PLAN.json"),
 capturedParent:read("nqc-037-historical-state/inputs/parent-header.json")});
engine.run({maxNewRequests:0}).then(result=>{
 console.log(JSON.stringify({commit,result,worker_events:engine.events(),commercial_admission:false},null,2));
 if(result.status!=="BLOCKED_RECOVERED_RECEIPT_REVIEW_REQUIRED"||result.responses_verified!==2||
    result.simulated_dispatches_this_run!==0)process.exitCode=2;
}).catch(()=>{console.log(JSON.stringify({status:"BLOCKED_OFFLINE_REPLAY",commercial_admission:false}));process.exitCode=2;});
