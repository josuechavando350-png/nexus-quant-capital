/* NQC052: NQC047/048 storage lifecycle -> complete NQC037 Python subprocess.
 * DRY_RUN only. No credential or arbitrary RPC/transport parameter is accepted.
 * runPython(raw) must launch worker.py in a fresh isolated Python process.
 */
(function(root){
"use strict";
const PLAN_SHA="6148b4248555043ec3276f3887e008974643ccff64f755b8b6ed986f8537d2f7";
const SPEC_SHA="fe1bd67bfedd84372e76da84840cd0d52db1906a461a668684b3388a8c006034";
const SCOPE="nqc048:dryrun:nqc052:authentic-verifier:fixed8";
const INTAKE_BLOB="c36d60ce83e73d246496bd0b72bc6cbe00d5893e";
function requireOk(value){if(!value)throw Error("NQC052_BINDING_REJECTED");}
const clone=x=>JSON.parse(JSON.stringify(x));
function journal(){return {schema:"nqc048-chunked-dryrun-v1",mode:"DRY_RUN",scope:SCOPE,
 plan_sha256:PLAN_SHA,spec_sha256:SPEC_SHA,max_requests:8,commercial_admission:false,entries:[]};}
function create({ledger,hash,store,spec,runPython,capturedParent,mode="DRY_RUN"}){
 requireOk(mode==="DRY_RUN"&&typeof runPython==="function");
 requireOk(hash(JSON.stringify(spec))===SPEC_SHA&&hash(JSON.stringify(spec.logical_requests))===PLAN_SHA);
 const plan=spec.logical_requests;
 let events=[];
 async function run({maxNewRequests=0}={}){
  requireOk(Number.isInteger(maxNewRequests)&&maxNewRequests>=0&&maxNewRequests<=8);
  // New prefix on EVERY invocation; no caller-supplied state can certify a predecessor.
  let prefix=[],active=false;
  const verify=async(op,response)=>{
   requireOk(!active&&op.request.id===prefix.length+1);
   requireOk(JSON.stringify(op)===JSON.stringify(plan[prefix.length]));
   active=true;
   try{
    const trial=[...prefix,clone(response)],raw=JSON.stringify({responses:trial});
    const reply=await runPython(raw);
    events.push({id:op.request.id,status:reply.status,responses_validated:reply.responses_validated,
     input_sha256:hash(raw),intake_git_blob:reply.intake_git_blob||null});
    requireOk(reply.input_sha256===hash(raw)&&reply.intake_git_blob===INTAKE_BLOB&&
      reply.complete_original_modules_loaded===true&&reply.status==="OFFLINE_PREFIX_VERIFIED"&&
      reply.responses_validated===trial.length&&reply.commercial_admission===false&&reply.live_enabled===false);
    prefix=trial;
   }finally{active=false;}
  };
  // Deliberately artificial input, NEVER an authenticated provider response.
  const transport=async op=>{
   const id=op.request.id;
   if(id===1)return {jsonrpc:"2.0",id,result:"0x1237"};
   if(id===2){
    requireOk(capturedParent?.id===6&&capturedParent?.result?.hash===plan[1].request.params[0]);
    return {jsonrpc:"2.0",id,result:clone(capturedParent.result)};
   }
   if(id===3)return {jsonrpc:"2.0",id,result:{address:op.request.params[0],
     nonce:"0x1",balance:"0x0",codeHash:"0x"+"11".repeat(32),storageHash:"0x"+"22".repeat(32),
     accountProof:["0xc0"],storageProof:[]}};
   throw Error("NQC052_NO_FOURTH_SYNTHETIC_INPUT");
  };
  const engine=ledger.create({store,hash,plan,scope:SCOPE,planSha256:PLAN_SHA,specSha256:SPEC_SHA,
    verify,transport,mode:"DRY_RUN"});
  return engine.run({maxNewRequests});
 }
 return {run,events:()=>clone(events)};
}
root.NQC052={create,journal,SCOPE,PLAN_SHA,SPEC_SHA};
if(typeof module!=="undefined"&&module.exports)module.exports=root.NQC052;
})(typeof globalThis!=="undefined"?globalThis:this);
