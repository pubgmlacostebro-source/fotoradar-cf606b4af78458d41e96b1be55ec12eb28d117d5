const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const script = fs.readFileSync(require('node:path').join(__dirname, '../docs/run-search.js'), 'utf8');
async function scenario(failDispatch) {
  const elements = new Map();
  const node = () => ({className:'btn', value:'', textContent:'', disabled:false, parentElement:{parentElement:{querySelector:()=>({})}}, replaceWith(item){elements.set('manualRunBtn',item)}, insertAdjacentElement(){}, showModal(){this.open=true}, close(){this.open=false}, querySelector(id){return get(id)}});
  const get = id => { if(!elements.has(id)) elements.set(id,node()); return elements.get(id); };
  get('manualRunBtn').replaceWith = item => elements.set('manualRunBtn',item);
  const calls=[]; let dispatched=false, loaded=false, expired=false;
  const saved = new Map();
  const context = {
    document:{ getElementById:get,createElement:node,body:{append(){}} },
    localStorage:{getItem:key=>saved.get(key)||null,setItem:(key,value)=>saved.set(key,value),removeItem:key=>saved.delete(key)},
    load:async()=>{loaded=true},setTimeout:fn=>{fn()},
    fetch:async(url,options={})=>{
      calls.push({url,options});
      const reply=(data,status=200)=>({ok:status<400,status,json:async()=>data});
      if(url.startsWith('data/')) return reply({checked:Math.ceil(Date.now()/1000)});
      if(expired) return reply(null,401);
      if(url.endsWith('/dispatches')) {dispatched=true;return reply(null,failDispatch?403:204)}
      if(url.includes('/runs?')) return reply({workflow_runs:dispatched?[{id:73,created_at:new Date().toISOString()}]:[]});
      if(url.endsWith('/runs/73')) return reply({status:'completed',conclusion:'success'});
      return reply({id:1});
    }
  };
  vm.runInNewContext(script,context);
  await get('manualRunBtn').onclick();
  assert.equal(calls.length,0,'no token must not send a request');
  get('#runToken').value='fake-test-token';
  await get('#runConnect').onclick();
  assert.equal(get('#runToken').value,'','clear input after connecting');
  await get('manualRunBtn').onclick();
  assert.equal(get('manualRunBtn').disabled,false,'restore button on every outcome');
  assert.equal(loaded,!failDispatch,'reload only after a successful run and publication');
  assert.equal(calls.filter(c=>c.url.endsWith('/dispatches')).length,1);
  for(const call of calls){
    assert.ok(!call.url.includes('fake-test-token'));
    if(call.url.startsWith('data/'))assert.equal(call.options.headers,undefined,'never send token to data URLs');
    else assert.equal(new URL(call.url).hostname,'api.github.com');
  }
  if(failDispatch)assert.match(get('refreshNote').textContent,/Ошибка/);
  if(!failDispatch){
    assert.equal(saved.size,1,'remember a validated key');
    elements.clear(); dispatched=false; loaded=false; calls.length=0;
    vm.runInNewContext(script,context);
    await get('manualRunBtn').onclick();
    assert.equal(loaded,true,'a fresh page can run without re-entering the key');
    get('#runDisconnect').onclick();
    assert.equal(saved.size,0,'forget deletes the saved key');
    elements.clear(); calls.length=0;
    vm.runInNewContext(script,context);
    await get('manualRunBtn').onclick();
    assert.equal(calls.length,0,'forgotten key stays absent after reload');
    get('#runToken').value='fake-test-token';
    await get('#runConnect').onclick();
    expired=true;
    await get('manualRunBtn').onclick();
    assert.equal(saved.size,0,'401 removes an expired key');
    assert.match(get('refreshNote').textContent,/истёк/);
  }
}
(async()=>{await scenario(false);await scenario(true);console.log('Direct search: success, denied dispatch, token isolation, reload persistence, forget, expiry, and button recovery passed.');})().catch(e=>{console.error(e);process.exitCode=1});
