"use strict";
const {test,after}=require('node:test'), assert=require('node:assert/strict'), fs=require('node:fs');
const {Model}=require('./ledger_model.js');
const evidence=[];
function scenario(name, fn) {test(name,async()=>{const m=new Model();try {await fn(m);}
  finally {evidence.push({name,...m.evidence()});m.close();}});}
scenario('eight independent simultaneous executors: one reservation winner',async m=>{
  const results=await Promise.all(Array.from({length:8},()=>m.run({barrier:8})));
  assert.equal(m.dispatches().length,1);
  assert.equal(new Set(m.events.filter(e=>e.kind==='commit'||e.kind==='cas_conflict').map(e=>e.pid)).size,8);
  assert.equal(results.filter(x=>x.status==='READY_FOR_NEXT_READ').length,1);
  assert.equal(results.filter(x=>x.status==='BLOCKED_AMBIGUOUS_JOURNAL').length,7);
});
scenario('process death after durable reservation burns slot and prevents replay',async m=>{
  assert.equal((await m.run({killAfter:'RESERVED'})).interrupted,true);
  assert.equal((await m.run()).status,'BLOCKED_PENDING_RESERVATION');
  assert.equal(m.dispatches().length,0);
});
scenario('process death at send: ambiguous attempt cannot be retried by another process',async m=>{
  await m.run({killAtDispatch:true});
  assert.equal((await m.run()).status,'BLOCKED_PENDING_RESERVATION');
  assert.equal(m.dispatches().length,1);
});
scenario('lost reservation confirmation: next independent executor also stops',async m=>{
  assert.equal((await m.run({loseAck:'RESERVED'})).status,'BLOCKED_AMBIGUOUS_JOURNAL');
  assert.equal((await m.run()).status,'BLOCKED_PENDING_RESERVATION');
  assert.equal(m.dispatches().length,0);
});
scenario('death after receipt: fresh process revalidates but does not dispatch',async m=>{
  await m.run({killAfter:'RECEIVED'});
  assert.equal((await m.run()).status,'BLOCKED_RECOVERED_RECEIPT_REVIEW_REQUIRED');
  assert.equal(m.dispatches().length,1);
  assert.equal(m.events.filter(e=>e.kind==='revalidated').length,1);
});
scenario('unchanged authority caps eight total across eight successive processes',async m=>{
  for(let i=0;i<8;i++) await m.run();
  assert.equal((await m.run()).status,'COMPLETE_DRY_RUN');
  assert.deepEqual(m.dispatches().map(x=>x.id),[1,2,3,4,5,6,7,8]);
});
scenario('COUNTEREXAMPLE local authority rollback permits ninth global attempt',async m=>{
  await m.run({maxNew:8});
  m.heads.canonical=m.initial; // simulator only; NO GitHub ref operation
  await m.run();
  assert.equal(m.dispatches().length,9);
  assert.deepEqual(m.dispatches().map(x=>x.id),[1,2,3,4,5,6,7,8,1]);
});
scenario('COUNTEREXAMPLE copied authority accepts two id1 attempts with identical scope',async m=>{
  m.heads.copy=m.initial;
  await Promise.all([m.run(),m.run({branch:'copy'})]);
  assert.deepEqual(m.dispatches().map(x=>x.id),[1,1]);
});
scenario('COUNTEREXAMPLE provider error is rejected without retaining response body',async m=>{
  assert.equal((await m.run({errorResponse:true})).status,'BLOCKED_REJECTED_STEP');
  assert.equal((await m.run()).status,'BLOCKED_REJECTED_STEP');
  assert.equal(m.dispatches().length,1);
  assert.deepEqual(m.state().parts,{});
  assert.equal(m.state().content.includes('SYNTHETIC PROVIDER ERROR'),false);
});
scenario('COUNTEREXAMPLE JSON object interface cannot retain original HTTP bytes',async m=>{
  await m.run();
  const saved=Buffer.from(m.state().parts['1:0'],'base64').toString();
  const wire='{ "jsonrpc": "2.0", "id": 1, "result": "SIMULATED" }\n';
  assert.deepEqual(JSON.parse(saved),JSON.parse(wire));
  assert.notEqual(saved,wire);
});
after(()=>{
  fs.mkdirSync(__dirname+'/evidence',{recursive:true});
  fs.writeFileSync(__dirname+'/evidence/ledger-scenarios.json',JSON.stringify({
    schema:'nqc053-independent-process-model-v1',scope:'LOCAL_SIMULATION_NOT_REMOTE_LIVE_PROOF',
    verifier:'SYNTHETIC_CONTROL_ONLY_NOT_NQC037',physical_hosts:1,
    scenarios:evidence,live_admission:false,commercial_admission:false,triport_requests_sent:0},null,2)+'\n');
});
