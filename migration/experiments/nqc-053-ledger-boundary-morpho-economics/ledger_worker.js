/* Independent OS-process executor of the unchanged NQC048 ledger.
 * IPC simulator only: no HTTP, credentials, RPC or live mode. */
"use strict";
const fs = require('node:fs');
const crypto = require('node:crypto');
const pins = JSON.parse(fs.readFileSync(__dirname+'/SOURCE_MANIFEST.json')).unchanged_control_sources;
for(const [name,pin] of Object.entries(pins)) {
  const raw=fs.readFileSync(__dirname+'/../'+name);
  if(crypto.createHash('sha256').update(raw).digest('hex')!==pin.sha256) throw Error('source changed');
}
const ledger = require('../nqc-048-durable-chunked-receipts/chunked_ledger.js');
const plan = JSON.parse(fs.readFileSync(__dirname + '/../nqc-038-archive-access/TRIPORT_PLAN.json')).logical_requests;
const hash = x => crypto.createHash('sha256').update(x).digest('hex');
let sequence = 0;
const pending = new Map();
process.on('message', m => {
  if (m.type !== 'reply') return;
  const p = pending.get(m.id); pending.delete(m.id);
  m.error ? p.reject(Error(m.error)) : p.resolve(m.value);
});
function rpc(method, ...args) {
  return new Promise((resolve, reject) => {
    const id = ++sequence; pending.set(id, {resolve, reject});
    process.send({type:'call', id, method, args});
  });
}
const store = Object.fromEntries(['head','at','put','writePart','readPart'].map(
  name => [name, (...args) => rpc(name,...args)]));
const engine = ledger.create({store, hash, plan,
  scope:'nqc048:dryrun:nqc053:fixed-lifetime-simulation',
  planSha256:hash(JSON.stringify(plan)), specSha256:hash('synthetic-control-only'),
  verify:async (op, response) => {
    // This deliberately does NOT authenticate historical state. NQC037 integration
    // is unchanged and already covered by NQC052. Only ledger interleavings are tested.
    if (response.id !== op.request.id || response.result !== 'SIMULATED') throw Error('fixture');
    await rpc('verified', op.request.id);
  }, transport:op => rpc('dispatch', op.request.id)});
engine.run({maxNewRequests:Number(process.argv[2])}).then(result => {
  process.send({type:'done', result}, () => process.disconnect());
}).catch(error => { process.send({type:'fatal', error:error.message}, () => process.disconnect()); });
