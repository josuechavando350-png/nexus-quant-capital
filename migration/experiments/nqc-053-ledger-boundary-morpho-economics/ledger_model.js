/* Local disk-backed model of a remote blob-CAS store, not a GitHub guarantee.
 * Only this test model can clone/rollback. No Git ref is changed here. */
"use strict";
const fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const crypto = require('node:crypto'), {fork} = require('node:child_process');
const hash = (x, alg='sha256') => crypto.createHash(alg).update(x).digest('hex');
const copy = x => JSON.parse(JSON.stringify(x));
const plan = JSON.parse(fs.readFileSync(__dirname + '/../nqc-038-archive-access/TRIPORT_PLAN.json')).logical_requests;
class Model {
  constructor() {
    this.dir = fs.mkdtempSync(path.join(os.tmpdir(),'nqc053-simulation-'));
    this.serial=0; this.heads={}; this.events=[]; this.children=new Set(); this.gates=[];
    this.initial = this.publish('canonical', {content:JSON.stringify({
      schema:'nqc048-chunked-dryrun-v1', mode:'DRY_RUN',
      scope:'nqc048:dryrun:nqc053:fixed-lifetime-simulation',
      plan_sha256:hash(JSON.stringify(plan)), spec_sha256:hash('synthetic-control-only'),
      max_requests:8, commercial_admission:false, entries:[]})+'\n', parts:{}});
  }
  publish(branch, state) {
    const sha=hash(state.content,'sha1');
    const commit=hash(JSON.stringify([++this.serial,state]),'sha1');
    const filename=path.join(this.dir,commit+'.json');
    const fd=fs.openSync(filename,'wx');
    try {fs.writeFileSync(fd,JSON.stringify({...state,sha}));fs.fsyncSync(fd);} finally {fs.closeSync(fd);}
    this.heads[branch]=commit;
    return commit;
  }
  read(commit) { return JSON.parse(fs.readFileSync(path.join(this.dir,commit+'.json'))); }
  state(branch='canonical') { return this.read(this.heads[branch]); }
  dispatches() { return this.events.filter(x=>x.kind==='dispatch'); }
  async action(child, branch, options, method, args) {
    if(method==='head') return this.heads[branch];
    if(method==='at') {const s=this.read(args[0]);return {sha:s.sha,content:s.content};}
    if(method==='readPart') return {content:this.read(args[0]).parts[args[1]+':'+args[2]]};
    if(method==='verified') {this.events.push({kind:'revalidated',pid:child.pid,id:args[0]});return true;}
    if(method==='put') {
      const next=JSON.parse(args[1]), last=next.entries.at(-1);
      // All competing processes have already read the same initial blob before
      // either CAS executes. This is a deterministic schedule, not a timing sleep.
      if(options.barrier && last?.status==='RESERVED') {
        await new Promise(resolve=>{
          this.gates.push(resolve);
          if(this.gates.length===options.barrier) this.gates.splice(0).forEach(f=>f());
        });
      }
      const old=this.state(branch);
      if(old.sha!==args[0]) {this.events.push({kind:'cas_conflict',pid:child.pid});throw Error('CAS conflict');}
      const commit=this.publish(branch,{content:args[1],parts:old.parts});
      this.events.push({kind:'commit',pid:child.pid,status:last?.status,id:last?.id,branch,commit});
      if(options.killAfter===last?.status) { child.kill('SIGKILL'); return undefined; }
      if(options.loseAck===last?.status) throw Error('simulated lost confirmation');
      return {commit_sha:commit};
    }
    if(method==='writePart') {
      const state=this.state(branch), key=args[0]+':'+args[1];
      if(key in state.parts) throw Error('part already exists');
      state.parts[key]=args[2];
      return {commit_sha:this.publish(branch,state)};
    }
    if(method==='dispatch') {
      const state=this.state(branch), id=args[0];
      if(JSON.parse(state.content).entries.at(-1)?.status!=='RESERVED') throw Error('not reserved');
      this.events.push({kind:'dispatch',pid:child.pid,id,branch,reservation_commit:this.heads[branch]});
      if(options.killAtDispatch) {child.kill('SIGKILL');return undefined;}
      if(options.errorResponse) return {jsonrpc:'2.0',id,error:{code:-32000,message:'SYNTHETIC PROVIDER ERROR'}};
      return {jsonrpc:'2.0',id,result:'SIMULATED'};
    }
    throw Error('unrecognized IPC action');
  }
  run(options={}) {
    const branch=options.branch||'canonical';
    const child=fork(path.join(__dirname,'ledger_worker.js'),[String(options.maxNew??1)],
      {stdio:['ignore','ignore','pipe','ipc'],execArgv:[]});
    this.children.add(child);
    return new Promise((resolve,reject)=>{
      let result, stderr='';
      const timeout=setTimeout(()=>{child.kill('SIGKILL');reject(Error('worker timed out'));},15000);
      child.stderr.on('data',s=>stderr+=s);
      child.on('message',async m=>{
        if(m.type==='done') {result=m.result;return;}
        if(m.type==='fatal') {result={fatal:m.error};return;}
        if(m.type!=='call') return;
        try {
          const value=await this.action(child,branch,options,m.method,m.args);
          if(child.connected&&!child.killed) child.send({type:'reply',id:m.id,value});
        } catch(error) {if(child.connected&&!child.killed) child.send({type:'reply',id:m.id,error:error.message});}
      });
      child.on('exit',(code,signal)=>{
        clearTimeout(timeout);this.children.delete(child);
        if(stderr) {reject(Error(stderr));return;}
        resolve(result||{interrupted:true,code,signal});
      });
    });
  }
  evidence() {return {events:copy(this.events),heads:copy(this.heads),
    journals:Object.fromEntries(Object.entries(this.heads).map(([b,h])=>[b,JSON.parse(this.read(h).content)])),
    simulated_dispatches:this.dispatches().length,triport_requests_sent:0};}
  close() { for(const c of this.children)c.kill('SIGKILL');fs.rmSync(this.dir,{recursive:true,force:true}); }
}
module.exports={Model};
