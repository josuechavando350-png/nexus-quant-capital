/* NQC047 remote acquisition ledger, fail-closed. No RPC or credential access.
   Adapter contract: head() -> commit SHA; at(commit) -> {sha,content};
   put(expectedBlobSha,content) -> {commit_sha}.
   Production proof validation is NOT supplied here. DRY_RUN only. */
(function(root){
"use strict";
const SCHEMA="nqc047-remote-ledger-v1";
const MAX_BYTES=650000;
const K=[0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
const rotr=(x,n)=>(x>>>n)|(x<<(32-n));
function utf8(s){const b=unescape(encodeURIComponent(s));return Array.from(b,c=>c.charCodeAt(0));}
function sha256(s){
 const b=utf8(s), bits=b.length*8; b.push(128);
 while(b.length%64!==56)b.push(0);
 const hi=Math.floor(bits/4294967296),lo=bits>>>0;
 for(const n of [hi,lo])for(let sh=24;sh>=0;sh-=8)b.push((n>>>sh)&255);
 const h=[0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
 for(let start=0;start<b.length;start+=64){
  const w=new Array(64);
  for(let i=0;i<16;i++){const q=start+4*i;w[i]=((b[q]<<24)|(b[q+1]<<16)|(b[q+2]<<8)|b[q+3])>>>0;}
  for(let i=16;i<64;i++){
   const a=w[i-15],z=w[i-2];
   w[i]=(w[i-16]+(rotr(a,7)^rotr(a,18)^(a>>>3))+w[i-7]+(rotr(z,17)^rotr(z,19)^(z>>>10)))>>>0;
  }
  let [a,c,d,e,f,g,j,k]=h;
  for(let i=0;i<64;i++){
   const s1=rotr(f,6)^rotr(f,11)^rotr(f,25), ch=(f&g)^(~f&j);
   const t1=(k+s1+ch+K[i]+w[i])>>>0;
   const s0=rotr(a,2)^rotr(a,13)^rotr(a,22), maj=(a&c)^(a&d)^(c&d);
   const t2=(s0+maj)>>>0;
   k=j;j=g;g=f;f=(e+t1)>>>0;e=d;d=c;c=a;a=(t1+t2)>>>0;
  }
  const v=[a,c,d,e,f,g,j,k];for(let i=0;i<8;i++)h[i]=(h[i]+v[i])>>>0;
 }
 return h.map(v=>v.toString(16).padStart(8,"0")).join("");
}
function serialize(x){const v=JSON.stringify(x);if(typeof v!=="string")throw Error("non-JSON");return v+"\n";}
function reject(message){throw Error("NQC047_PROTOCOL_"+message);}
function engine({store,plan,scope,planSha256,mode="DRY_RUN",verify,transport}){
 if(mode!=="DRY_RUN")reject("LIVE_DISABLED");
 if(!store||!Array.isArray(plan)||plan.length!==8||typeof verify!=="function")reject("INIT");
 if(typeof scope!=="string"||!scope.startsWith("nqc047:dryrun:"))reject("SCOPE");
 if(sha256(JSON.stringify(plan))!==planSha256)reject("PLAN_BINDING");
 for(let i=0;i<8;i++){
  const p=plan[i];if(!p||!p.request||p.request.id!==i+1||!p.purpose)reject("PLAN_IDS");
 }
 const clone=x=>JSON.parse(JSON.stringify(x));
 const output=(status,j,dispatched=0,verified=0)=>({
   status,attempt_slots_reserved:j.entries.length,responses_verified:verified,
   remaining_attempt_slots:8-j.entries.length,simulated_dispatches_this_run:dispatched,
   commercial_admission:false,historical_state_proofs_acquired:0
 });
 function check(j){
  if(!j||j.schema!==SCHEMA||j.mode!=="DRY_RUN"||j.scope!==scope||
     j.plan_sha256!==planSha256||j.max_requests!==8||j.commercial_admission!==false||
     !Array.isArray(j.entries)||j.entries.length>8)reject("JOURNAL_BINDING");
  for(let i=0;i<j.entries.length;i++){
   const r=j.entries[i],p=plan[i];
   if(!r||r.id!==i+1||r.purpose!==p.purpose||
      !["RESERVED","RECEIVED","VERIFIED","REJECTED"].includes(r.status))reject("ENTRY");
   if(i<j.entries.length-1&&r.status!=="VERIFIED")reject("ORDER");
   const has=Object.prototype.hasOwnProperty.call(r,"response");
   if(has){
    if(typeof r.response_sha256!=="string"||
       sha256(JSON.stringify(r.response))!==r.response_sha256)reject("RESPONSE_DIGEST");
   }else if(Object.prototype.hasOwnProperty.call(r,"response_sha256"))reject("RESPONSE_SCHEMA");
   if(["RECEIVED","VERIFIED"].includes(r.status)&&!has)reject("MISSING_RESPONSE");
   if(r.status==="RESERVED"&&has)reject("RESERVED_HAS_RESPONSE");
  }
  return j;
 }
 async function snapshot(){
  const tip=await store.head(), obj=await store.at(tip);
  if(!obj||typeof obj.sha!=="string"||typeof obj.content!=="string")reject("READBACK");
  const j=check(JSON.parse(obj.content));
  return {tip,sha:obj.sha,j};
 }
 async function persist(old,next){
  const payload=serialize(check(next));
  if(utf8(payload).length>MAX_BYTES)return {error:"BLOCKED_JOURNAL_SIZE"};
  try{
   const out=await store.put(old.sha,payload);
   if(!out||typeof out.commit_sha!=="string")return {error:"BLOCKED_AMBIGUOUS_WRITE"};
   const reread=await store.at(out.commit_sha);
   if(!reread||reread.content!==payload||
      (await store.head())!==out.commit_sha)return {error:"BLOCKED_AMBIGUOUS_CONFIRMATION"};
   return {tip:out.commit_sha,sha:reread.sha,j:check(JSON.parse(reread.content))};
  }catch(_){return {error:"BLOCKED_AMBIGUOUS_WRITE"};}
 }
 async function run({maxNewRequests=0,secret=null}={}){
  if(!Number.isInteger(maxNewRequests)||maxNewRequests<0||maxNewRequests>8)reject("BUDGET_ARGUMENT");
  if(maxNewRequests&&typeof transport!=="function")reject("NO_SIMULATOR");
  let snap;
  try{snap=await snapshot();}catch(_){return {status:"BLOCKED_UNREADABLE_LEDGER",commercial_admission:false};}
  let dispatched=0,verified=0,state={};
  for(let i=0;i<8;i++){
   const p=plan[i];let r=snap.j.entries[i];
   if(r){
    if(r.status==="RESERVED")return output("BLOCKED_AMBIGUOUS_ATTEMPT",snap.j,dispatched,verified);
    if(r.status==="REJECTED")return output("BLOCKED_REJECTED_STEP",snap.j,dispatched,verified);
    try{if(!r.response||sha256(JSON.stringify(r.response))!==r.response_sha256)
       return output("BLOCKED_RESPONSE_INTEGRITY",snap.j,dispatched,verified);
       await verify(p,clone(r.response),state);
    }catch(_){return output("BLOCKED_REVALIDATION",snap.j,dispatched,verified);}
    verified++;
    if(r.status==="RECEIVED"){
      const next=clone(snap.j);next.entries[i].status="VERIFIED";
      const committed=await persist(snap,next);
      if(committed.error)return output(committed.error,snap.j,dispatched,verified);
      snap=committed;
    }
    continue;
   }
   if(dispatched>=maxNewRequests)return output("READY_FOR_NEXT_READ",snap.j,dispatched,verified);
   let next=clone(snap.j);
   next.entries.push({id:i+1,purpose:p.purpose,status:"RESERVED"});
   let committed=await persist(snap,next);
   if(committed.error)return output(committed.error,snap.j,dispatched,verified);
   snap=committed; // Verified remote persistence before any transport call.
   dispatched++;
   let response;
   try{
    response=await transport(clone(p));
    const encoded=JSON.stringify(response);
    if(typeof encoded!=="string"||utf8(encoded).length>MAX_BYTES||
       (typeof secret==="string"&&secret.length>0&&encoded.includes(secret)))reject("RESPONSE_UNSAFE");
    if(!response||response.jsonrpc!=="2.0"||response.id!==i+1||
       !Object.prototype.hasOwnProperty.call(response,"result")||
       Object.prototype.hasOwnProperty.call(response,"error"))reject("ENVELOPE");
   }catch(_){
    next=clone(snap.j);next.entries[i].status="REJECTED";
    committed=await persist(snap,next);
    return output(committed.error||"BLOCKED_REJECTED_STEP",committed.j||snap.j,dispatched,verified);
   }
   next=clone(snap.j);
   next.entries[i]={id:i+1,purpose:p.purpose,status:"RECEIVED",
      response:clone(response),response_sha256:sha256(JSON.stringify(response))};
   committed=await persist(snap,next);
   if(committed.error)return output(committed.error,snap.j,dispatched,verified);
   snap=committed; // Response has been durably stored before validation/next step.
   try{await verify(p,clone(response),state);}catch(_){
    next=clone(snap.j);next.entries[i].status="REJECTED";
    committed=await persist(snap,next);
    return output(committed.error||"BLOCKED_REJECTED_STEP",committed.j||snap.j,dispatched,verified);
   }
   verified++;
   next=clone(snap.j);next.entries[i].status="VERIFIED";
   committed=await persist(snap,next);
   if(committed.error)return output(committed.error,snap.j,dispatched,verified);
   snap=committed;
  }
  return output("COMPLETE_DRY_RUN",snap.j,dispatched,verified);
 }
 return {run,sha256,check};
}
root.NQC047Ledger={engine,sha256,SCHEMA,MAX_BYTES};
if(typeof module!=="undefined"&&module.exports)module.exports=root.NQC047Ledger;
})(typeof globalThis!=="undefined"?globalThis:this);
