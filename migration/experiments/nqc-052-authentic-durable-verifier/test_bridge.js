/* Tests the unchanged NQC048 engine with actual NQC037 in fresh Python processes.
 * The storage fault model is local. GitHub evidence is recorded separately.
 */
"use strict";
const assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path");
const {spawnSync}=require("node:child_process"),crypto=require("node:crypto");
const bridge=require("./authentic_bridge.js");
const ledger=require("../nqc-048-durable-chunked-receipts/chunked_ledger.js");
const hash=require("../nqc-047-remote-ledger/ledger_engine.js").sha256;
const adapter=require("./github_store.js");
const repo=path.resolve(__dirname,"../../.."),experiments=path.join(repo,"migration/experiments");
const spec=JSON.parse(fs.readFileSync(path.join(experiments,"nqc-038-archive-access/TRIPORT_PLAN.json")));
const capturedParent=JSON.parse(fs.readFileSync(path.join(experiments,"nqc-037-historical-state/inputs/parent-header.json")));
const clone=x=>JSON.parse(JSON.stringify(x));
function runPython(raw){
 const p=spawnSync(process.env.NQC052_PYTHON||"python",["-I",path.join(__dirname,"worker.py"),"--repo-root",repo],
  {input:raw,encoding:"utf8",maxBuffer:1024*1024,timeout:20000});
 assert.equal(p.stderr,"");assert.ok([0,2].includes(p.status));return JSON.parse(p.stdout);
}
function memoryStore(){
 let n=0,tip="0".repeat(40),text=JSON.stringify(bridge.journal())+"\n",parts={},fault=null;
 const gitBlob=s=>crypto.createHash("sha1").update("blob "+Buffer.byteLength(s)+"\0"+s).digest("hex");
 let sha=gitBlob(text),history=new Map();
 const save=()=>history.set(tip,{content:text,sha,parts:clone(parts)});save();
 const commit=()=>{tip=(++n).toString(16).padStart(40,"0");save();return {commit_sha:tip};};
 return {head:async()=>tip,at:async id=>{assert.ok(history.has(id));return clone(history.get(id));},
  async put(expected,content){
   assert.equal(expected,sha);text=content;sha=gitBlob(text);const ack=commit();
   if(fault?.(content))throw Error("INJECTED_ACK_LOSS");return ack;
  },
  async writePart(id,index,content){const key=id+":"+index;assert.ok(!(key in parts));parts[key]=content;return commit();},
  async readPart(commit,id,index){const content=history.get(commit)?.parts[id+":"+index];assert.equal(typeof content,"string");return {content};},
  fault:f=>{fault=f;},get journal(){return JSON.parse(text);},get chunkCount(){return Object.keys(parts).length;}
 };
}
const make=store=>bridge.create({ledger,hash,store,spec,runPython,capturedParent});
async function main(){
 const results=[];
 async function test(name,fn){try{const result=await fn();results.push({name,pass:true,...result});}
  catch(e){results.push({name,pass:false,error:String(e)});}}
 await test("real verifier accepts two persisted fixtures then rejects third proof before fourth",async()=>{
  const s=memoryStore(),e=make(s),a=await e.run({maxNewRequests:8});
  assert.equal(a.status,"BLOCKED_REJECTED_STEP");assert.equal(a.simulated_dispatches_this_run,3);
  assert.equal(a.responses_verified,2);assert.deepEqual(s.journal.entries.map(x=>x.status),["VERIFIED","VERIFIED","REJECTED"]);
  const b=await make(s).run({maxNewRequests:8});
  assert.equal(b.simulated_dispatches_this_run,0);assert.equal(b.responses_verified,2);assert.equal(s.chunkCount,3);
  return {first:a,restart:b,authentic_calls:e.events()};
 });
 await test("fresh process rebuilds prefix across successive runs",async()=>{
  const s=memoryStore(),e=make(s);
  assert.equal((await e.run({maxNewRequests:1})).responses_verified,1);
  assert.equal((await e.run({maxNewRequests:1})).responses_verified,2);
  const b=await make(s).run({maxNewRequests:0});
  assert.equal(b.responses_verified,2);assert.equal(b.simulated_dispatches_this_run,0);
 });
 await test("lost RECEIVED ack revalidates actual Python but cannot release another request",async()=>{
  const s=memoryStore();s.fault(content=>JSON.parse(content).entries.at(-1)?.status==="RECEIVED");
  const a=await make(s).run({maxNewRequests:8});assert.equal(a.status,"BLOCKED_AMBIGUOUS_JOURNAL");
  s.fault(null);const e=make(s),b=await e.run({maxNewRequests:8});
  assert.equal(b.status,"BLOCKED_RECOVERED_RECEIPT_REVIEW_REQUIRED");assert.equal(b.responses_verified,1);
  assert.equal(b.simulated_dispatches_this_run,0);assert.equal(s.journal.entries[0].status,"RECEIVED");
  assert.equal(e.events()[0].intake_git_blob,"c36d60ce83e73d246496bd0b72bc6cbe00d5893e");
 });
 await test("lost reserve ack does not call Python or simulator",async()=>{
  const s=memoryStore();s.fault(content=>JSON.parse(content).entries.at(-1)?.status==="RESERVED");
  const e=make(s),a=await e.run({maxNewRequests:8});
  assert.equal(a.simulated_dispatches_this_run,0);assert.equal(e.events().length,0);
  s.fault(null);assert.equal((await make(s).run({maxNewRequests:8})).status,"BLOCKED_PENDING_RESERVATION");
 });
 await test("700KB receipt is reconstructed and genuinely revalidated without transport",async()=>{
  const s=memoryStore(),source=JSON.stringify({jsonrpc:"2.0",id:1,result:"0x1237",padding:"X".repeat(700000)});
  const raw=Buffer.from(source),parts=[];
  for(let offset=0,i=0;offset<raw.length;offset+=ledger.CHUNK_BYTES,i++){
   const chunk=raw.subarray(offset,offset+ledger.CHUNK_BYTES),b64=chunk.toString("base64");
   await s.writePart(1,i,b64);parts.push({b64_sha256:hash(b64),bytes:chunk.length});
  }
  const j=bridge.journal();j.entries.push({id:1,purpose:"chain",status:"RECEIVED",
   receipt:{byte_length:raw.length,sha256:hash(source),parts}});
  await s.put((await s.at(await s.head())).sha,JSON.stringify(j)+"\n");
  const b=await make(s).run({maxNewRequests:8});
  assert.equal(b.status,"BLOCKED_RECOVERED_RECEIPT_REVIEW_REQUIRED");assert.equal(b.responses_verified,1);
  assert.equal(b.simulated_dispatches_this_run,0);assert.equal(parts.length,3);
  return {bytes:raw.length,parts:parts.length,result:b};
 });
 await test("corrupt stored chunks stop before any new synthetic request",async()=>{
  const s=memoryStore();await make(s).run({maxNewRequests:1});
  s.readPart=async()=>({content:"AAAA"});const b=await make(s).run({maxNewRequests:8});
  assert.equal(b.status,"BLOCKED_REVALIDATION");assert.equal(b.simulated_dispatches_this_run,0);
 });
 await test("worker result digest mismatch cannot authorize next step",async()=>{
  const s=memoryStore(),e=bridge.create({ledger,hash,store:s,spec,capturedParent,
   runPython:raw=>({...runPython(raw),input_sha256:"0".repeat(64)})});
  const a=await e.run({maxNewRequests:8});assert.equal(a.simulated_dispatches_this_run,1);
  assert.equal(a.status,"BLOCKED_REJECTED_STEP");
 });
 await test("LIVE and modified fixed plan refused",async()=>{
  assert.throws(()=>bridge.create({ledger,hash,store:memoryStore(),spec,runPython,capturedParent,mode:"LIVE"}));
  const changed=clone(spec);changed.maximum_requests=9;
  assert.throws(()=>bridge.create({ledger,hash,store:memoryStore(),spec:changed,runPython,capturedParent}));
 });
 await test("current connector structured response is required; fixed paths and conditional SHA",async()=>{
  const head="a".repeat(40),blob="b".repeat(40),commit="c".repeat(40),calls=[];
  const wrap=x=>({structuredContent:x});
  const tools={mcp__codex_apps__github_fetch:async arg=>{calls.push(arg);return wrap({content:JSON.stringify({object:{sha:head}})});},
   mcp__codex_apps__github_fetch_file:async arg=>{calls.push(arg);return wrap({sha:blob,content:"data",encoding:"utf-8"});},
   mcp__codex_apps__github_update_file:async arg=>{calls.push(arg);return wrap({commit_sha:commit});},
   mcp__codex_apps__github_create_file:async arg=>{calls.push(arg);return wrap({commit_sha:commit});}};
  const s=adapter.create(tools);assert.equal(await s.head(),head);await s.at(head);await s.put(blob,"{}");
  await s.writePart(1,0,"YQ==");await s.readPart(head,1,0);
  assert.equal(calls[2].sha,blob);assert.equal(calls[2].branch,adapter.BRANCH);
  assert.equal(calls[3].path,adapter.chunkPath(1,0));assert.equal(calls[4].ref,head);
  tools.mcp__codex_apps__github_update_file=async()=>({isError:true});
  await assert.rejects(()=>s.put(blob,"{}"));assert.throws(()=>adapter.chunkPath(9,0));
 });
 const report={passed:results.filter(x=>x.pass).length,failed:results.filter(x=>!x.pass).length,
  results,triport_requests_sent:0,commercial_admission:false};
 console.log(JSON.stringify(report,null,2));if(report.failed)process.exitCode=1;
}
main().catch(e=>{console.error(String(e));process.exitCode=1;});
