/* Executed in Work code mode, where connected GitHub and exec_command coexist.
 * Load pinned NQC047, NQC048, authentic_bridge.js and github_store.js first.
 * All provider inputs are fixed synthetic fixtures in authentic_bridge.js.
 */
(function(root){
"use strict";
const quote=s=>"'"+s.replaceAll("'","'\\''")+"'";
async function run({tools,repoRoot,python,spec,capturedParent,maxNewRequests=0,loseReceivedAck=false}){
 const writes=[],store=root.NQC052GitHub.create(tools),originalPut=store.put;
 let injected=false;
 store.put=async(expected,content)=>{
  const ack=await originalPut(expected,content),j=JSON.parse(content);
  writes.push({commit:ack.commit_sha,status:j.entries.at(-1).status,id:j.entries.at(-1).id});
  if(loseReceivedAck&&!injected&&j.entries.at(-1).status==="RECEIVED"){
   injected=true;throw Error("SYNTHETIC_LOST_ACK_AFTER_SUCCESSFUL_REMOTE_WRITE");
  }
  return ack;
 };
 const runPython=async raw=>{
  // POSIX quoting: JSON is stdin data, never interpreted by the shell.
  // printf preserves exact bytes; a heredoc would add a digest-changing newline.
  const cmd="printf %s "+quote(raw)+" | "+quote(python)+" -I "+
   quote(repoRoot+"/migration/experiments/nqc-052-authentic-durable-verifier/worker.py")+
   " --repo-root "+quote(repoRoot);
  const r=await tools.exec_command({cmd,max_output_tokens:2500});
  if(![0,2].includes(r.exit_code))throw Error("WORKER_PROCESS_FAILED");
  return JSON.parse(r.output);
 };
 const e=root.NQC052.create({ledger:root.NQC048,hash:root.NQC047Ledger.sha256,
  store,spec,runPython,capturedParent});
 const initialHead=await store.head(),result=await e.run({maxNewRequests}),finalHead=await store.head();
 const saved=await store.at(finalHead);
 return {initial_head:initialHead,final_head:finalHead,result,writes,
  injected_ack_loss:injected,worker_events:e.events(),journal:JSON.parse(saved.content),
  provider_inputs:"SYNTHETIC_ONLY_NOT_ACQUIRED_FROM_TRIPORT",commercial_admission:false};
}
root.NQC052Probe={run};
if(typeof module!=="undefined"&&module.exports)module.exports=root.NQC052Probe;
})(typeof globalThis!=="undefined"?globalThis:this);
