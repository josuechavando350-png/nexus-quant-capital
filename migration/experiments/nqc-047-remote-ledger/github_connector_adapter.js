/* NQC047 connector adapter: pinned repository, branch and journal.
   For use inside an authorized ChatGPT GitHub connector executor only.
   Never creates branches or sessions; never retries a failed update.
   No RPC, secret, workflow or external process calls. */
(function(root){
"use strict";
const REPO="josuechavando350-png/nexus-quant-capital";
const BRANCH="research/nqc-047-remote-ledger-20261019";
const PATH="migration/experiments/nqc-047-remote-ledger/evidence/DRYRUN_JOURNAL.json";
function pinnedGitHubStore(tools){
 if(!tools||typeof tools.mcp__GitHub__fetch_commit!=="function"||
    typeof tools.mcp__GitHub__fetch_file!=="function"||
    typeof tools.mcp__GitHub__update_file!=="function")throw Error("GitHub connector unavailable");
 return {
  async head(){
   const out=await tools.mcp__GitHub__fetch_commit({repo_full_name:REPO,commit_sha:BRANCH});
   const sha=out?.result?.commit?.sha;
   if(!/^[0-9a-f]{40}$/.test(sha||""))throw Error("Unconfirmed head");
   return sha;
  },
  async at(commitSha){
   if(!/^[0-9a-f]{40}$/.test(commitSha||""))throw Error("Exact commit required");
   const out=await tools.mcp__GitHub__fetch_file({
     repository_full_name:REPO,path:PATH,ref:commitSha,encoding:"utf-8"});
   const obj=out?.result;
   if(!obj||typeof obj.content!=="string"||!/^[0-9a-f]{40}$/.test(obj.sha||""))
     throw Error("Unconfirmed file");
   return {sha:obj.sha,content:obj.content};
  },
  async put(expectedBlobSha,content){
   if(!/^[0-9a-f]{40}$/.test(expectedBlobSha||"")||typeof content!=="string")
     throw Error("Invalid write arguments");
   const out=await tools.mcp__GitHub__update_file({
     repository_full_name:REPO,branch:BRANCH,path:PATH,sha:expectedBlobSha,
     content,message:"NQC047: DRY_RUN ledger transition"});
   const commit_sha=out?.result?.commit_sha;
   if(!/^[0-9a-f]{40}$/.test(commit_sha||""))throw Error("Unconfirmed update");
   return {commit_sha};
  }
 };
}
root.NQC047GitHub={pinnedGitHubStore,REPO,BRANCH,PATH};
if(typeof module!=="undefined"&&module.exports)module.exports=root.NQC047GitHub;
})(typeof globalThis!=="undefined"?globalThis:this);
