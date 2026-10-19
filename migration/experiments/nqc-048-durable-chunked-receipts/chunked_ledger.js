/* NQC048 chunked GitHub receipt ledger. DRY_RUN only. No live RPC or secrets.
 * Code depends on pinned NQC047 SHA-256 helper, NEVER a replacement verifier.
 * A recovered RECEIVED receipt is revalidated but NOT cleared for new dispatch.
 */
(function(root){
"use strict";
const SCHEMA="nqc048-chunked-dryrun-v1";
const MAX_RESPONSE_BYTES=16*1024*1024;
const CHUNK_BYTES=256*1024; // 349528 base64 characters, below GitHub Contents limits
const MAX_LEDGER_BYTES=650000;
const BASE64="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
const hex64=x=>typeof x==="string"&&/^[0-9a-f]{64}$/.test(x);
function enc64(bytes){
 let out=[];
 for(let i=0;i<bytes.length;i+=3){
  const a=bytes.charCodeAt(i),hasB=i+1<bytes.length,hasC=i+2<bytes.length;
  const b=hasB?bytes.charCodeAt(i+1):0,c=hasC?bytes.charCodeAt(i+2):0;
  out.push(BASE64[a>>>2],BASE64[((a&3)<<4)|(b>>>4)],
    hasB?BASE64[((b&15)<<2)|(c>>>6)]:"=",
    hasC?BASE64[c&63]:"=");
 }
 return out.join("");
}
function dec64(text){
 if(typeof text!=="string"||text.length%4!==0||!/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(text))
   throw Error("Invalid base64");
 let chars=[];
 for(let i=0;i<text.length;i+=4){
  const a=BASE64.indexOf(text[i]),b=BASE64.indexOf(text[i+1]);
  const c=text[i+2]==="="?0:BASE64.indexOf(text[i+2]);
  const d=text[i+3]==="="?0:BASE64.indexOf(text[i+3]);
  if(a<0||b<0||c<0||d<0)throw Error("Invalid base64 symbols");
  chars.push(String.fromCharCode((a<<2)|(b>>>4)));
  if(text[i+2]!=="=")chars.push(String.fromCharCode(((b&15)<<4)|(c>>>2)));
  if(text[i+3]!=="=")chars.push(String.fromCharCode(((c&3)<<6)|d));
 }
 return chars.join("");
}
function utf8(x){return unescape(encodeURIComponent(x));}
function fromUtf8(x){return decodeURIComponent(escape(x));}
function canonical(x){const s=JSON.stringify(x);if(typeof s!=="string")throw Error("Not JSON");return s;}
function clone(x){return JSON.parse(canonical(x));}
function fail(code){throw Error("NQC048_"+code);}
function create({store,hash,plan,scope,planSha256,specSha256,verify,transport,mode="DRY_RUN"}){
 if(mode!=="DRY_RUN")fail("LIVE_FORBIDDEN");
 if(typeof hash!=="function"||!store||typeof verify!=="function"||!Array.isArray(plan)||plan.length!==8)
   fail("BAD_CONFIGURATION");
 if(typeof scope!=="string"||!scope.startsWith("nqc048:dryrun:"))fail("SCOPE");
 if(!hex64(planSha256)||hash(canonical(plan))!==planSha256||!hex64(specSha256))fail("BINDING");
 for(let i=0;i<plan.length;i++){
  const op=plan[i];
  if(!op||!op.request||op.request.id!==i+1||typeof op.purpose!=="string"||!op.purpose)
    fail("PLAN_ORDER");
 }
 const ROOT_KEYS="commercial_admission,entries,max_requests,mode,plan_sha256,schema,scope,spec_sha256";
 const RECEIPT_KEYS="byte_length,parts,sha256";
 const KEYS={RESERVED:"id,purpose,status",REJECTED:"id,purpose,status",
   RECEIVED:"id,purpose,receipt,status",VERIFIED:"id,purpose,receipt,status"};
 function names(x){return Object.keys(x).sort().join(",");}
 function check(j){
  if(!j||typeof j!=="object"||names(j)!==ROOT_KEYS||
     j.schema!==SCHEMA||j.mode!=="DRY_RUN"||j.scope!==scope||j.plan_sha256!==planSha256||
     j.spec_sha256!==specSha256||j.max_requests!==8||j.commercial_admission!==false||
     !Array.isArray(j.entries)||j.entries.length>8)fail("JOURNAL_SCHEMA");
  j.entries.forEach((row,index)=>{
   if(!row||typeof row!=="object"||row.id!==index+1||
      row.purpose!==plan[index].purpose||!KEYS[row.status]||names(row)!==KEYS[row.status])
      fail("STEP_SCHEMA");
   if(index<j.entries.length-1&&row.status!=="VERIFIED")fail("NONTERMINAL_PREFIX");
   if(["RECEIVED","VERIFIED"].includes(row.status)){
    const receipt=row.receipt;
    if(!receipt||names(receipt)!==RECEIPT_KEYS||!hex64(receipt.sha256)||
       !Number.isInteger(receipt.byte_length)||receipt.byte_length<1||
       receipt.byte_length>MAX_RESPONSE_BYTES||
       !Array.isArray(receipt.parts)||receipt.parts.length<1||
       receipt.parts.length>Math.ceil(MAX_RESPONSE_BYTES/CHUNK_BYTES))fail("RECEIPT_SCHEMA");
    let total=0;
    receipt.parts.forEach((part,i)=>{
     if(!part||names(part)!=="b64_sha256,bytes"||!hex64(part.b64_sha256)||
        !Number.isInteger(part.bytes)||part.bytes<1||part.bytes>CHUNK_BYTES||
        (i<receipt.parts.length-1&&part.bytes!==CHUNK_BYTES))fail("PART_SCHEMA");
     total+=part.bytes;
    });
    if(total!==receipt.byte_length)fail("RECEIPT_LENGTH");
   }
  });
  return j;
 }
 async function snapshot(){
  const tip=await store.head(),obj=await store.at(tip);
  if(typeof tip!=="string"||!/^[0-9a-f]{40}$/.test(tip)||!obj||
     typeof obj.sha!=="string"||typeof obj.content!=="string")fail("READBACK");
  return {tip,sha:obj.sha,j:check(JSON.parse(obj.content))};
 }
 async function persist(old,next){
  let payload;
  try{
   payload=canonical(check(next))+"\n";
   if(utf8(payload).length>MAX_LEDGER_BYTES)return {error:"BLOCKED_LEDGER_CAP"};
   const committed=await store.put(old.sha,payload);
   if(!committed||!/^[0-9a-f]{40}$/.test(committed.commit_sha||""))return{error:"BLOCKED_AMBIGUOUS_JOURNAL"};
   const saved=await store.at(committed.commit_sha);
   if(!saved||saved.content!==payload||(await store.head())!==committed.commit_sha)
     return{error:"BLOCKED_AMBIGUOUS_JOURNAL"};
   return {tip:committed.commit_sha,sha:saved.sha,j:check(JSON.parse(saved.content))};
  }catch(_){return{error:"BLOCKED_AMBIGUOUS_JOURNAL"};}
 }
 function out(status,j,calls=0,verified=0){
  return {status,attempt_slots_reserved:j.entries.length,
    responses_verified:verified,remaining_attempt_slots:8-j.entries.length,
    simulated_dispatches_this_run:calls,triport_requests_sent:0,
    historical_state_proofs_acquired:0,commercial_admission:false};
 }
 async function saveReceipt(id,response,secret){
  const source=canonical(response);
  if(typeof secret==="string"&&secret.length&&source.includes(secret))fail("SECRET_ECHO");
  const raw=utf8(source);
  if(raw.length>MAX_RESPONSE_BYTES)fail("RESPONSE_TOO_BIG");
  const parts=[];
  for(let i=0,offset=0;offset<raw.length;i++,offset+=CHUNK_BYTES){
   const bin=raw.slice(offset,offset+CHUNK_BYTES);
   const base64=enc64(bin);
   // The provider response has already arrived, so failure MUST NOT initiate a retry.
   const ack=await store.writePart(id,i,base64);
   if(!ack||!/^[0-9a-f]{40}$/.test(ack.commit_sha||""))fail("PART_CONFIRMATION");
   const saved=await store.readPart(ack.commit_sha,id,i);
   if(!saved||saved.content!==base64||(await store.head())!==ack.commit_sha)
     fail("PART_READBACK");
   parts.push({b64_sha256:hash(base64),bytes:bin.length});
  }
  if(!parts.length)fail("EMPTY_RECEIPT");
  return {sha256:hash(source),byte_length:raw.length,parts};
 }
 async function restore(head,id,receipt){
  let binary="";
  for(let i=0;i<receipt.parts.length;i++){
   const part=receipt.parts[i],f=await store.readPart(head,id,i);
   if(!f||typeof f.content!=="string"||hash(f.content)!==part.b64_sha256)
     fail("CHUNK_INTEGRITY");
   const decoded=dec64(f.content);
   if(decoded.length!==part.bytes)fail("CHUNK_LENGTH");
   binary+=decoded;
  }
  if(binary.length!==receipt.byte_length)fail("TOTAL_LENGTH");
  const raw=fromUtf8(binary);
  if(hash(raw)!==receipt.sha256)fail("RESPONSE_SHA");
  const response=JSON.parse(raw);
  if(response===null||typeof response!=="object"||Array.isArray(response))fail("RESPONSE_TYPE");
  if(response.jsonrpc!=="2.0"||response.id!==id||
     !Object.prototype.hasOwnProperty.call(response,"result")||
      Object.prototype.hasOwnProperty.call(response,"error"))fail("ENVELOPE");
  return response;
 }
 async function run({maxNewRequests=0,secret=null}={}){
  if(!Number.isInteger(maxNewRequests)||maxNewRequests<0||maxNewRequests>8)fail("BUDGET");
  if(maxNewRequests&&!transport)fail("NO_SIMULATOR");
  let snap;
  try{snap=await snapshot();}catch(_){
   return{status:"BLOCKED_UNREADABLE_LEDGER",commercial_admission:false,triport_requests_sent:0};
  }
  let sent=0,verified=0,state={};
  for(let i=0;i<8;i++){
   const row=snap.j.entries[i],op=plan[i],id=i+1;
   if(row){
    if(row.status==="RESERVED")return out("BLOCKED_PENDING_RESERVATION",snap.j,sent,verified);
    if(row.status==="REJECTED")return out("BLOCKED_REJECTED_STEP",snap.j,sent,verified);
    let response;
    try{
     response=await restore(snap.tip,id,row.receipt);
     await verify(clone(op),response,state);
    }catch(_){return out("BLOCKED_REVALIDATION",snap.j,sent,verified);}
    verified++;
    if(row.status==="RECEIVED")return out("BLOCKED_RECOVERED_RECEIPT_REVIEW_REQUIRED",snap.j,sent,verified);
    continue;
   }
   if(sent>=maxNewRequests)return out("READY_FOR_NEXT_READ",snap.j,sent,verified);
   let next=clone(snap.j);
   next.entries.push({id,purpose:op.purpose,status:"RESERVED"});
   let saved=await persist(snap,next);
   if(saved.error)return out(saved.error,snap.j,sent,verified);
   snap=saved;
   sent++;
   let response;
   try{
    response=await transport(clone(op));
    const body=canonical(response);
    if(!response||response.jsonrpc!=="2.0"||response.id!==id||
       !Object.prototype.hasOwnProperty.call(response,"result")||
       Object.prototype.hasOwnProperty.call(response,"error")||
       (typeof secret==="string"&&secret.length&&body.includes(secret)))fail("ENVELOPE_OR_SECRET");
   }catch(_){
    next=clone(snap.j);next.entries[i].status="REJECTED";
    saved=await persist(snap,next);
    return out(saved.error||"BLOCKED_REJECTED_STEP",saved.j||snap.j,sent,verified);
   }
   let receipt;
   try{receipt=await saveReceipt(id,response,secret);}
   catch(_){return out("BLOCKED_UNCONFIRMED_RECEIPT",snap.j,sent,verified);}
   next=clone(snap.j);next.entries[i]={id,purpose:op.purpose,status:"RECEIVED",receipt};
   saved=await persist(snap,next);
   if(saved.error)return out(saved.error,snap.j,sent,verified);
   snap=saved;
   try{
    const fromGit=await restore(snap.tip,id,receipt);
    await verify(clone(op),fromGit,state);
   }catch(_){
    next=clone(snap.j);next.entries[i].status="REJECTED";delete next.entries[i].receipt;
    saved=await persist(snap,next);
    return out(saved.error||"BLOCKED_REJECTED_STEP",saved.j||snap.j,sent,verified);
   }
   verified++;
   next=clone(snap.j);next.entries[i].status="VERIFIED";
   saved=await persist(snap,next);
   if(saved.error)return out(saved.error,snap.j,sent,verified);
   snap=saved;
  }
  return out("COMPLETE_DRY_RUN",snap.j,sent,verified);
 }
 return {run,check,snapshot,restore};
}
root.NQC048={create,enc64,dec64,utf8,fromUtf8,SCHEMA,MAX_RESPONSE_BYTES,CHUNK_BYTES};
if(typeof module!=="undefined"&&module.exports)module.exports=root.NQC048;
})(typeof globalThis!=="undefined"?globalThis:this);
