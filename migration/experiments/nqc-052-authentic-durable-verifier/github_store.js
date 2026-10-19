/* Fixed NQC052 experimental journal using current connected GitHub APIs.
 * This is NOT a LIVE/global quota registry. No initializer, retries or ref reset.
 */
(function(root){
"use strict";
const REPO="josuechavando350-png/nexus-quant-capital";
const BRANCH="research/nqc-052-authentic-durable-verifier-20261019";
const PREFIX="migration/experiments/nqc-052-authentic-durable-verifier/evidence/remote/";
const JOURNAL=PREFIX+"JOURNAL.json";
const valid=x=>typeof x==="string"&&/^[0-9a-f]{40}$/.test(x);
function unwrap(r){
 if(r?.isError)throw Error("CONNECTOR_ERROR");
 const v=r?.structuredContent;
 if(!v||typeof v!=="object")throw Error("CONNECTOR_SCHEMA");
 return v;
}
function chunkPath(id,index){
 if(!Number.isInteger(id)||id<1||id>8||!Number.isInteger(index)||index<0||index>63)
  throw Error("CHUNK_COORDINATES");
 return PREFIX+"receipts/"+String(id).padStart(2,"0")+"/part-"+String(index).padStart(3,"0")+".b64";
}
function create(tools){
 async function head(){
  const r=unwrap(await tools.mcp__codex_apps__github_fetch({
   url:"https://api.github.com/repos/"+REPO+"/git/ref/heads/"+BRANCH}));
  const sha=JSON.parse(r.content)?.object?.sha;
  if(!valid(sha))throw Error("UNCONFIRMED_HEAD");return sha;
 }
 async function fileAt(commit,path){
  if(!valid(commit))throw Error("EXACT_COMMIT_REQUIRED");
  const f=unwrap(await tools.mcp__codex_apps__github_fetch_file({repository_full_name:REPO,path,ref:commit}));
  if(!valid(f.sha)||typeof f.content!=="string"||f.encoding!=="utf-8")throw Error("FILE_SCHEMA");
  return {sha:f.sha,content:f.content};
 }
 function ack(r){const v=unwrap(r);if(!valid(v.commit_sha))throw Error("UNCONFIRMED_WRITE");return {commit_sha:v.commit_sha};}
 return {head,at:commit=>fileAt(commit,JOURNAL),
  async put(expected,content){
   if(!valid(expected)||typeof content!=="string")throw Error("INVALID_CAS");
   return ack(await tools.mcp__codex_apps__github_update_file({repository_full_name:REPO,
    branch:BRANCH,path:JOURNAL,sha:expected,content,message:"NQC052: synthetic journal transition"}));
  },
  async writePart(id,index,content){
   if(typeof content!=="string"||content.length>400000||!/^[A-Za-z0-9+/]*={0,2}$/.test(content))
    throw Error("INVALID_CHUNK");
   return ack(await tools.mcp__codex_apps__github_create_file({repository_full_name:REPO,
    branch:BRANCH,path:chunkPath(id,index),content,message:"NQC052: immutable synthetic receipt "+id+"/"+index}));
  },
  readPart:(commit,id,index)=>fileAt(commit,chunkPath(id,index))};
}
root.NQC052GitHub={create,REPO,BRANCH,JOURNAL,chunkPath};
if(typeof module!=="undefined"&&module.exports)module.exports=root.NQC052GitHub;
})(typeof globalThis!=="undefined"?globalThis:this);
