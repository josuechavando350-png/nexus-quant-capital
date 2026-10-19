/* NQC048 GitHub connector adapter. This is ONLY a DRY_RUN fixture.
 * One fixed experimental journal, explicit file-SHA conditional updates,
 * immutable per-request chunk paths, fresh readback by exact commit SHA.
 * Never sends RPC, expands permissions, creates a new budget or uses a key.
 */
(function(root){
"use strict";
const REPO="josuechavando350-png/nexus-quant-capital";
const BRANCH="research/nqc-048-durable-chunked-receipts-20261019";
const PREFIX="migration/experiments/nqc-048-durable-chunked-receipts/evidence/";
const JOURNAL=PREFIX+"JOURNAL.json";
function chunkPath(id,index){
 if(!Number.isInteger(id)||id<1||id>8||!Number.isInteger(index)||index<0||index>63)
   throw Error("Invalid receipt coordinates");
 return PREFIX+"receipts/"+String(id).padStart(2,"0")+"/part-"+String(index).padStart(3,"0")+".b64";
}
function pinnedGitHubStore(tools){
 const methodNames=["fetch_commit","fetch_file","update_file","create_file"];
 for(const name of methodNames){
  if(!tools||typeof tools["mcp__GitHub__"+name]!=="function")
    throw Error("Missing GitHub connector action "+name);
 }
 async function head(){
  const r=await tools.mcp__GitHub__fetch_commit({repo_full_name:REPO,commit_sha:BRANCH});
  const sha=r?.result?.commit?.sha;
  if(!/^[0-9a-f]{40}$/.test(sha||""))throw Error("Unconfirmed branch head");
  return sha;
 }
 async function fileAt(commit,path){
  if(!/^[0-9a-f]{40}$/.test(commit||""))throw Error("Invalid commit");
  const r=await tools.mcp__GitHub__fetch_file({repository_full_name:REPO,path,ref:commit,encoding:"utf-8"});
  const f=r?.result;
  if(!f||typeof f.content!=="string"||!/^[0-9a-f]{40}$/.test(f.sha||""))
    throw Error("Unconfirmed file");
  return{sha:f.sha,content:f.content};
 }
 return {
  head,
  at:commit=>fileAt(commit,JOURNAL),
  async put(expected,content){
   if(!/^[0-9a-f]{40}$/.test(expected||"")||typeof content!=="string")throw Error("Invalid journal CAS");
   const r=await tools.mcp__GitHub__update_file({repository_full_name:REPO,branch:BRANCH,path:JOURNAL,
     sha:expected,content,message:"NQC048: DRY_RUN journal conditional transition"});
   const commit_sha=r?.result?.commit_sha;
   if(!/^[0-9a-f]{40}$/.test(commit_sha||""))throw Error("Journal commit unconfirmed");
   return{commit_sha};
  },
  async writePart(id,index,base64){
   if(typeof base64!=="string"||base64.length>400000||!/^[A-Za-z0-9+/]*={0,2}$/.test(base64))
     throw Error("Invalid chunk payload");
   const r=await tools.mcp__GitHub__create_file({
    repository_full_name:REPO,branch:BRANCH,path:chunkPath(id,index),content:base64,
    message:"NQC048: DRY_RUN immutable receipt chunk "+id+"/"+index});
   const commit_sha=r?.result?.commit_sha;
   if(!/^[0-9a-f]{40}$/.test(commit_sha||""))throw Error("Chunk commit unconfirmed");
   return{commit_sha};
  },
  readPart:(commit,id,index)=>fileAt(commit,chunkPath(id,index))
 };
}
root.NQC048GitHub={pinnedGitHubStore,REPO,BRANCH,JOURNAL,chunkPath};
if(typeof module!=="undefined"&&module.exports)module.exports=root.NQC048GitHub;
})(typeof globalThis!=="undefined"?globalThis:this);
