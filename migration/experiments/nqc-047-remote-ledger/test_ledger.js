/* NQC047 offline regression suite. NO RPC, financial operations or secrets.
   Node: node migration/experiments/nqc-047-remote-ledger/test_ledger.js
   Also injectable into a connector evaluator via NQC047Tests.run({mod,plan}). */
(function(root){
"use strict";
async function run({mod,plan}){
 const results=[],scope="nqc047:dryrun:chain4663:parent66744161:txindex1:fixed8:20261019";
 const planSha256=mod.sha256(JSON.stringify(plan));
 function assert(ok,msg){if(!ok)throw Error(msg||"assertion failed");}
 function journal(){return {schema:mod.SCHEMA,mode:"DRY_RUN",scope,plan_sha256:planSha256,
   max_requests:8,commercial_admission:false,entries:[]};}
 function fake(initial){
  let revision=0,tip="0".repeat(40),sha="s0",content=JSON.stringify(initial)+"\n",writes=0;
  let fault=null;const versions={[tip]:{sha,content}};
  return {
   async head(){return tip;},
   async at(id){if(!versions[id])throw Error("unknown commit");return {...versions[id]};},
   async put(expected,next){
    writes++;
    if(fault&&fault.when===writes&&fault.kind==="before")throw Error("simulated failure before persistence");
    if(fault&&fault.when===writes&&fault.kind==="stale"){
     const competitor=JSON.parse(content);
     competitor.entries.push({id:1,purpose:plan[0].purpose,status:"RESERVED"});
     next=JSON.stringify(competitor)+"\n";
     revision++;tip=revision.toString(16).padStart(40,"0");sha="s"+revision;content=next;
     versions[tip]={sha,content};throw Error("stale expected sha");
    }
    if(expected!==sha)throw Error("conditional write mismatch");
    revision++;tip=revision.toString(16).padStart(40,"0");sha="s"+revision;content=next;
    versions[tip]={sha,content};
    if(fault&&fault.when===writes&&fault.kind==="after")throw Error("response lost after persistence");
    return {commit_sha:tip};
   },
   fault(kind,when){fault=kind?{kind,when}:null;},
   get writes(){return writes;},
   get data(){return JSON.parse(content);}
  };
 }
 const validate=async(op,r,state)=>{
  if(r.result!=="SIM_ACCEPTED_"+op.request.id||(
      state.last!==undefined&&state.last!==op.request.id-1))throw Error("synthetic rejection");
  state.last=op.request.id;
 };
 const ack=op=>({jsonrpc:"2.0",id:op.request.id,result:"SIM_ACCEPTED_"+op.request.id});
 const mk=(s,t=ack,verify=validate)=>mod.engine({store:s,plan,scope,planSha256,verify,transport:t});
 async function one(name,task){
  try{const extra=await task();results.push({name,pass:true,...extra});}
  catch(e){results.push({name,pass:false,error:String(e)});}
 }
 await one("standard SHA-256 vectors and pinned plan",async()=>{
  assert(mod.sha256("abc")==="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
  assert(mod.sha256("")==="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
  assert(planSha256==="6148b4248555043ec3276f3887e008974643ccff64f755b8b6ed986f8537d2f7");
  return{};
 });
 await one("eight ordered reserves and no ninth request",async()=>{
  const s=fake(journal()),ids=[];const e=mk(s,op=>{ids.push(op.request.id);return ack(op);});
  const a=await e.run({maxNewRequests:8}),b=await e.run({maxNewRequests:8});
  assert(a.status==="COMPLETE_DRY_RUN"&&b.status==="COMPLETE_DRY_RUN");
  assert(ids.join(",")==="1,2,3,4,5,6,7,8"&&s.writes===24&&b.simulated_dispatches_this_run===0);
  return{simulated_calls:ids.length,commits:s.writes};
 });
 await one("persistent pending reservation prevents any dispatch",async()=>{
  const j=journal();j.entries=[{id:1,purpose:plan[0].purpose,status:"RESERVED"}];
  let calls=0;const out=await mk(fake(j),()=>{calls++;return ack(plan[0]);}).run({maxNewRequests:8});
  assert(out.status==="BLOCKED_AMBIGUOUS_ATTEMPT"&&calls===0);return{};
 });
 await one("lost reservation acknowledgement is terminal on recovery",async()=>{
  const s=fake(journal());s.fault("after",1);let calls=0;
  const e=mk(s,()=>{calls++;return ack(plan[0]);});
  const a=await e.run({maxNewRequests:8});s.fault(null);
  const b=await e.run({maxNewRequests:8});
  assert(a.status==="BLOCKED_AMBIGUOUS_WRITE"&&b.status==="BLOCKED_AMBIGUOUS_ATTEMPT"&&calls===0);
  return{};
 });
 await one("transport exception consumes one attempted slot without retry",async()=>{
  const s=fake(journal());let calls=0;const e=mk(s,()=>{calls++;throw Error("synthetic transport fault");});
  const a=await e.run({maxNewRequests:8}),b=await e.run({maxNewRequests:8});
  assert(a.status==="BLOCKED_REJECTED_STEP"&&b.status==="BLOCKED_REJECTED_STEP"&&calls===1);
  return{};
 });
 await one("stale conditional update cannot dispatch",async()=>{
  const s=fake(journal());s.fault("stale",1);let calls=0;
  const a=await mk(s,()=>{calls++;return ack(plan[0]);}).run({maxNewRequests:8});
  assert(a.status==="BLOCKED_AMBIGUOUS_WRITE"&&calls===0);return{};
 });
 await one("persisted receipt revalidates without re-sending",async()=>{
  const s=fake(journal());s.fault("after",2);let calls=0;
  const e=mk(s,op=>{calls++;return ack(op);});
  const a=await e.run({maxNewRequests:8});s.fault(null);
  const b=await e.run({maxNewRequests:0});
  assert(a.status==="BLOCKED_AMBIGUOUS_WRITE"&&b.status==="READY_FOR_NEXT_READ");
  assert(b.responses_verified===1&&calls===1);return{};
 });
 await one("corrupted response digest stops before transport",async()=>{
  const j=journal(),r=ack(plan[0]);
  j.entries=[{id:1,purpose:plan[0].purpose,status:"VERIFIED",response:r,response_sha256:"a".repeat(64)}];
  let calls=0;const a=await mk(fake(j),()=>{calls++;return ack(plan[0]);}).run({maxNewRequests:8});
  assert(a.status==="BLOCKED_UNREADABLE_LEDGER"&&calls===0);return{};
 });
 await one("cached invalid proof fails fresh revalidation",async()=>{
  const j=journal(),r={jsonrpc:"2.0",id:1,result:"NOT_PROVEN"};
  j.entries=[{id:1,purpose:plan[0].purpose,status:"VERIFIED",response:r,
    response_sha256:mod.sha256(JSON.stringify(r))}];
  let calls=0;const a=await mk(fake(j),()=>{calls++;return ack(plan[0]);}).run({maxNewRequests:8});
  assert(a.status==="BLOCKED_REVALIDATION"&&calls===0);return{};
 });
 await one("credential reflection is never committed",async()=>{
  const s=fake(journal());
  const e=mk(s,op=>({jsonrpc:"2.0",id:op.request.id,result:"FAKE_SECRET_PROBE_123456"}));
  const a=await e.run({maxNewRequests:8,secret:"FAKE_SECRET_PROBE_123456"});
  assert(a.status==="BLOCKED_REJECTED_STEP");
  assert(!JSON.stringify(s.data).includes("FAKE_SECRET_PROBE_123456"));return{};
 });
 await one("envelope mismatch stops the next request",async()=>{
  const s=fake(journal()),e=mk(s,()=>({jsonrpc:"2.0",id:999,result:"SIM_ACCEPTED_1"}));
  const a=await e.run({maxNewRequests:8});
  assert(a.status==="BLOCKED_REJECTED_STEP"&&s.data.entries.length===1);return{};
 });
 await one("synthetic validator rejects unauthenticated payload",async()=>{
  const s=fake(journal()),e=mk(s,()=>({jsonrpc:"2.0",id:1,result:"UNAUTHENTICATED"}));
  const a=await e.run({maxNewRequests:8});
  assert(a.status==="BLOCKED_REJECTED_STEP"&&s.data.entries.length===1);
  assert(!!s.data.entries[0].response_sha256);return{};
 });
 await one("plan mismatch forbids startup",async()=>{
  let caught=false;try{mod.engine({store:fake(journal()),plan,scope,planSha256:"0".repeat(64),verify:validate});}
  catch(_){caught=true;}assert(caught);return{};
 });
 await one("invalid budget and LIVE mode reject",async()=>{
  const s=fake(journal()),e=mk(s);
  let caught=0;
  try{await e.run({maxNewRequests:9});}catch(_){caught++;}
  try{mod.engine({store:s,plan,scope,planSha256,verify:validate,mode:"LIVE"});}catch(_){caught++;}
  assert(caught===2);return{};
 });
 await one("failed write before reservation never invokes transport",async()=>{
  const s=fake(journal());s.fault("before",1);let calls=0;
  const a=await mk(s,()=>{calls++;return ack(plan[0]);}).run({maxNewRequests:8});
  assert(a.status==="BLOCKED_AMBIGUOUS_WRITE"&&calls===0&&s.data.entries.length===0);return{};
 });
 return{passed:results.filter(r=>r.pass).length,failed:results.filter(r=>!r.pass).length,results};
}
root.NQC047Tests={run};
if(typeof module!=="undefined"&&module.exports){
 module.exports=root.NQC047Tests;
 if(typeof require!=="undefined"&&require.main===module){
  const fs=require("fs"),path=require("path");
  const mod=require("./ledger_engine.js");
  const plan=JSON.parse(fs.readFileSync(path.join(__dirname,"../nqc-038-archive-access/TRIPORT_PLAN.json"),"utf8")).logical_requests;
  run({mod,plan}).then(r=>{console.log(JSON.stringify(r,null,2));if(r.failed)process.exitCode=1;})
  .catch(e=>{console.error(String(e));process.exitCode=1;});
 }
}
})(typeof globalThis!=="undefined"?globalThis:this);
