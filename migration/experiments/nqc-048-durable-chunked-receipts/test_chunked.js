/* NQC048 offline regression suite. No secrets, external network or real RPC.
 * Run from checkout: node migration/experiments/nqc-048-durable-chunked-receipts/test_chunked.js
 * Or execute via injected NQC048Tests.run({engine,hash,plan,specSha256}).
 */
(function(root){
"use strict";
async function run({engine,hash,plan,specSha256}){
 const results=[],scope="nqc048:dryrun:4663:66744161:txindex1:fixed8",planSha256=hash(JSON.stringify(plan));
 function assert(condition,detail){if(!condition)throw Error(detail||"Assertion failed");}
 function journal(){return{schema:engine.SCHEMA,mode:"DRY_RUN",scope,plan_sha256:planSha256,
   spec_sha256:specSha256,max_requests:8,commercial_admission:false,entries:[]};}
 const clone=x=>JSON.parse(JSON.stringify(x));
 function memoryStore(initial){
  let revision=0,head="0".repeat(40),data=JSON.stringify(initial)+"\n",sha=hash(data).slice(0,40);
  let parts={},writes=0,partWrites=0,failed=null,corrupt=null;
  const history={[head]:{data,sha,parts:clone(parts)}};
  function commit(){
   revision++;head=revision.toString(16).padStart(40,"0");
   history[head]={data,sha,parts:clone(parts)};
   return{commit_sha:head};
  }
  const api={
   head:async()=>head,
   async at(id){if(!history[id])throw Error("Missing commit");return{sha:history[id].sha,content:history[id].data};},
   async put(expected,content){
    writes++;
    if(expected!==sha)throw Error("Blob CAS mismatch");
    if(failed?.action==="before-journal"&&failed?.phase===writes)throw Error("Simulated prewrite failure");
    if(failed?.action==="stale"&&failed?.phase===writes){
     const o=journal();o.entries=[{id:1,purpose:plan[0].purpose,status:"RESERVED"}];
     data=JSON.stringify(o)+"\n";sha=hash(data).slice(0,40);commit();throw Error("Simulated competitor");
    }
    data=content;sha=hash(data).slice(0,40);const out=commit();
    if(failed?.action==="after-journal"&&failed?.phase===writes)throw Error("Lost acknowledgement");
    if(failed?.action==="after-received"&&content.includes('"status":"RECEIVED"'))
      throw Error("Lost receipt journal acknowledgement");
    return out;
   },
   async writePart(id,index,content){
    partWrites++;
    const path=id+":"+index;
    if(Object.prototype.hasOwnProperty.call(parts,path))throw Error("Cannot overwrite response part");
    parts[path]=content;const out=commit();
    if(failed?.action==="after-part"&&failed?.phase===partWrites)throw Error("Lost chunk acknowledgement");
    return out;
   },
   async readPart(commitId,id,index){
    const obj=history[commitId];
    if(!obj)throw Error("Missing commit");
    const path=id+":"+index;
    if(!Object.prototype.hasOwnProperty.call(obj.parts,path))throw Error("Missing part");
    return{content:corrupt===path?"invalid_base64_payload":obj.parts[path]};
   },
   fail(action,phase){failed={action,phase};},
   clearFault(){failed=null;},
   corrupt(id,index){corrupt=id+":"+index;},
   get journal(){return JSON.parse(data);},
   get journalWrites(){return writes;},
   get chunkWrites(){return partWrites;},
   get blobData(){return parts;}
  };
  return api;
 }
 const ack=op=>({jsonrpc:"2.0",id:op.request.id,result:"SIM_ACCEPTED_"+op.request.id});
 const validator=async(op,response,state)=>{
  if(response.result!=="SIM_ACCEPTED_"+op.request.id)throw Error("Invalid synthetic receipt");
  if(state.previous!==undefined&&state.previous!==op.request.id-1)throw Error("Wrong order");
  state.previous=op.request.id;
 };
 const create=(store,transport=ack,verify=validator)=>engine.create({
  store,hash,plan,scope,planSha256,specSha256,verify,transport});
 async function one(name,fn){try{const stats=await fn();results.push({name,pass:true,...stats});}
    catch(e){results.push({name,pass:false,reason:String(e)});}}
 await one("unicode/base64 binary codec",async()=>{
  for(const source of ["","abc","ñ—☃🔥","multiple👨‍💻😀unpaired but valid","x".repeat(85000)+"😀"]){
   assert(engine.fromUtf8(engine.dec64(engine.enc64(engine.utf8(source))))===source,"Round trip");
  }
  return{};
 });
 await one("fixed eight requests and no ninth despite restart",async()=>{
  const s=memoryStore(journal()),ids=[];
  const e=create(s,op=>{ids.push(op.request.id);return ack(op);});
  const a=await e.run({maxNewRequests:8}),b=await e.run({maxNewRequests:8});
  assert(a.status==="COMPLETE_DRY_RUN"&&b.status==="COMPLETE_DRY_RUN","Not complete");
  assert(ids.join(",")==="1,2,3,4,5,6,7,8"&&s.journalWrites===24&&s.chunkWrites===8,"Wrong count");
  assert(b.simulated_dispatches_this_run===0&&a.commercial_admission===false,"Unexpected retry");
  return{simulated_calls:ids.length,chunks:s.chunkWrites,journal_commits:s.journalWrites};
 });
 await one("larger-than-NQC047 response split and recovered",async()=>{
  const s=memoryStore(journal()),big="A".repeat(700000);let calls=0;
  const e=create(s,op=>{calls++;return{...ack(op),padding:big};});
  const a=await e.run({maxNewRequests:1}),b=await e.run({maxNewRequests:0});
  assert(a.status==="READY_FOR_NEXT_READ"&&b.responses_verified===1&&calls===1,"No complete receipt");
  assert(s.chunkWrites>=3&&s.journal.entries[0].receipt.byte_length>650000,"Not actually chunked");
  return{response_bytes:s.journal.entries[0].receipt.byte_length,parts:s.chunkWrites,simulated_calls:calls};
 });
 await one("pending reservation blocks without transport",async()=>{
  const j=journal();j.entries=[{id:1,purpose:plan[0].purpose,status:"RESERVED"}];
  let calls=0;const a=await create(memoryStore(j),()=>{calls++;return ack(plan[0]);}).run({maxNewRequests:8});
  assert(a.status==="BLOCKED_PENDING_RESERVATION"&&calls===0);return{};
 });
 await one("lost reservation acknowledgement locks recovered session",async()=>{
  const s=memoryStore(journal());s.fail("after-journal",1);let calls=0;
  const e=create(s,op=>{calls++;return ack(op);});
  const a=await e.run({maxNewRequests:8});s.clearFault();
  const b=await e.run({maxNewRequests:8});
  assert(a.status==="BLOCKED_AMBIGUOUS_JOURNAL"&&b.status==="BLOCKED_PENDING_RESERVATION"&&calls===0);
  return{};
 });
 await one("stale CAS blocks before any simulated transport",async()=>{
  const s=memoryStore(journal());s.fail("stale",1);let calls=0;
  const a=await create(s,op=>{calls++;return ack(op);}).run({maxNewRequests:8});
  assert(a.status==="BLOCKED_AMBIGUOUS_JOURNAL"&&calls===0);return{};
 });
 await one("lost chunk acknowledgement leaves reserved status",async()=>{
  const s=memoryStore(journal());s.fail("after-part",1);let calls=0;
  const e=create(s,op=>{calls++;return ack(op);});
  const a=await e.run({maxNewRequests:8});s.clearFault();
  const b=await e.run({maxNewRequests:8});
  assert(a.status==="BLOCKED_UNCONFIRMED_RECEIPT"&&b.status==="BLOCKED_PENDING_RESERVATION"&&calls===1);
  return{};
 });
 await one("lost RECEIVED journal acknowledgement revalidates but will not resume dispatch",async()=>{
  const s=memoryStore(journal());s.fail("after-received");let calls=0,validations=0;
  const e=create(s,op=>{calls++;return ack(op);},async(op,r,state)=>{validations++;await validator(op,r,state);});
  const a=await e.run({maxNewRequests:8});s.clearFault();
  const b=await e.run({maxNewRequests:8});
  assert(a.status==="BLOCKED_AMBIGUOUS_JOURNAL","Missing ack block");
  assert(b.status==="BLOCKED_RECOVERED_RECEIPT_REVIEW_REQUIRED"&&calls===1,"Unsafe resume");
  assert(validations===1&&s.journal.entries[0].status==="RECEIVED","No recovered verification");
  return{};
 });
 await one("corrupted persisted chunk fails before next transport",async()=>{
  const s=memoryStore(journal()),e=create(s);
  const a=await e.run({maxNewRequests:1});assert(a.status==="READY_FOR_NEXT_READ");
  s.corrupt(1,0);let calls=0;
  const b=await create(s,()=>{calls++;return ack(plan[0]);}).run({maxNewRequests:8});
  assert(b.status==="BLOCKED_REVALIDATION"&&calls===0);return{};
 });
 await one("unsupported payload rejected by synthetic verifier after durable receipt",async()=>{
  const s=memoryStore(journal());let calls=0;
  const a=await create(s,op=>{calls++;return{...ack(op),result:"INVALID_SYNTHETIC"};}).run({maxNewRequests:8});
  assert(a.status==="BLOCKED_REJECTED_STEP"&&calls===1&&s.journal.entries[0].status==="REJECTED");
  assert(s.chunkWrites===1,"No evidence persisted");return{};
 });
 await one("invalid JSON-RPC envelope blocked before chunk storage",async()=>{
  const s=memoryStore(journal()),a=await create(s,()=>({jsonrpc:"2.0",id:99,result:"x"})).run({maxNewRequests:8});
  assert(a.status==="BLOCKED_REJECTED_STEP"&&s.chunkWrites===0);return{};
 });
 await one("synthetic key echo is not stored in durable receipt",async()=>{
  const s=memoryStore(journal()),marker="ONLY_FAKE_TOKEN_SAFETY_CHECK";
  const a=await create(s,op=>({...ack(op),token:marker})).run({maxNewRequests:8,secret:marker});
  assert(a.status==="BLOCKED_REJECTED_STEP"&&s.chunkWrites===0&&s.journal.entries.length===1);
  return{};
 });
 await one("transport failure consumes reserve without retry",async()=>{
  const s=memoryStore(journal());let calls=0;
  const e=create(s,()=>{calls++;throw Error("OFFLINE_TRANSPORT_EXCEPTION");});
  const a=await e.run({maxNewRequests:8}),b=await e.run({maxNewRequests:8});
  assert(a.status==="BLOCKED_REJECTED_STEP"&&b.status==="BLOCKED_REJECTED_STEP"&&calls===1);
  return{};
 });
 await one("forged plan, malformed journal and forbidden LIVE all halt",async()=>{
  let count=0,s=memoryStore(journal());
  try{engine.create({store:s,hash,plan,scope,planSha256:"0".repeat(64),specSha256,verify:validator,mode:"DRY_RUN"});}catch(_){count++;}
  try{engine.create({store:s,hash,plan,scope,planSha256,specSha256,verify:validator,mode:"LIVE"});}catch(_){count++;}
  const j=journal();j.entries=[{id:1,purpose:plan[0].purpose,status:"VERIFIED",extra:"malicious"}];
  const b=await create(memoryStore(j)).run({maxNewRequests:8});
  assert(count===2&&b.status==="BLOCKED_UNREADABLE_LEDGER");return{};
 });
 await one("revalidation forbids silent tamper of an authenticated predecessor",async()=>{
  const s=memoryStore(journal());await create(s).run({maxNewRequests:1});
  let calls=0;
  const e=create(s,()=>{calls++;return ack(plan[0]);},async()=>{throw Error("Test verifier mismatch");});
  const a=await e.run({maxNewRequests:1});
  assert(a.status==="BLOCKED_REVALIDATION"&&calls===0);return{};
 });
 return{passed:results.filter(x=>x.pass).length,failed:results.filter(x=>!x.pass).length,
  results,scope,plan_sha256:planSha256,spec_sha256:specSha256};
}
root.NQC048Tests={run};
if(typeof module!=="undefined"&&module.exports){
 module.exports=root.NQC048Tests;
 if(typeof require!=="undefined"&&require.main===module){
  const fs=require("fs"),path=require("path");
  const engine=require("./chunked_ledger.js"),hash=require("../nqc-047-remote-ledger/ledger_engine.js").sha256;
  const spec=JSON.parse(fs.readFileSync(path.join(__dirname,"../nqc-038-archive-access/TRIPORT_PLAN.json"),"utf8"));
  run({engine,hash,plan:spec.logical_requests,specSha256:hash(JSON.stringify(spec))})
    .then(x=>{console.log(JSON.stringify(x,null,2));if(x.failed)process.exitCode=1;})
    .catch(e=>{console.error(String(e));process.exitCode=1;});
 }
}
})(typeof globalThis!=="undefined"?globalThis:this);
