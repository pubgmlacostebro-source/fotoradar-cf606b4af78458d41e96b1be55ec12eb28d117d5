const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync(path.join(__dirname, '../docs/index.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const saved = new Map([['hidden', JSON.stringify(['old'])], ['fotoradar:github-token:test', 'unrelated-test-key']]);
const rows = ['old','new'].map(id => ({id,src:'rss',url:'https://example.org/'+id,text:'Заявка '+id,place:'Екатеринбург',author:'',tags:[],ts:Math.floor(Date.now()/1000)}));
async function openPage() {
  const nodes = new Map(), events = new Map();
  const get = id => {
    if(!nodes.has(id)) nodes.set(id,{value:'',innerHTML:'',textContent:'',hidden:false,addEventListener(){},setAttribute(k,v){this[k]=v}});
    return nodes.get(id);
  };
  get('searchAge').value='0'; get('searchType').value='all';
  const context = vm.createContext({
    document:{getElementById:get,addEventListener:(event,fn)=>events.set(event,fn)},
    localStorage:{getItem:k=>saved.get(k)||null,setItem:(k,v)=>saved.set(k,v)},
    window:{},navigator:{},setInterval(){},
    fetch:async url=>({ok:true,json:async()=>url.startsWith('data/leads')?rows:url.startsWith('data/sources')?{sources:[]}:{checked:1,sources:{}}}),
  });
  vm.runInContext(script,context);
  await vm.runInContext('load()',context);
  return {get, click:dataset=>events.get('click')({target:{closest:()=>({dataset})}})};
}
(async()=>{
  let page=await openPage();
  assert.ok(!page.get('feed').innerHTML.includes('https://example.org/old'));
  assert.equal(page.get('hiddenViewBtn').textContent,'Скрытые (1)');
  page.get('hiddenViewBtn').onclick();
  assert.ok(page.get('feed').innerHTML.includes('https://example.org/old'),'legacy hidden post remains accessible');
  assert.ok(page.get('feed').innerHTML.includes('Вернуть в ленту'));
  page.click({restore:'old'}); page.get('activeViewBtn').onclick();
  assert.ok(page.get('feed').innerHTML.includes('https://example.org/old'));
  page.click({hide:'new'});
  assert.equal(page.get('hideNotice').hidden,false);
  assert.ok(!page.get('feed').innerHTML.includes('https://example.org/new'));
  page.get('undoHideBtn').onclick();
  assert.ok(page.get('feed').innerHTML.includes('https://example.org/new'));
  page.click({hide:'new'}); page.click({hide:'old'});
  assert.ok(page.get('feed').innerHTML.includes('Объявления скрыты'),'all-hidden feed must explain recovery');
  page=await openPage(); page.get('hiddenViewBtn').onclick();
  assert.equal((page.get('feed').innerHTML.match(/<article/g)||[]).length,2,'hidden posts survive reload');
  page.get('restoreAllBtn').onclick();
  assert.equal((page.get('feed').innerHTML.match(/<article/g)||[]).length,2);
  assert.deepEqual(JSON.parse(saved.get('hidden')),[]);
  assert.equal(saved.get('fotoradar:github-token:test'),'unrelated-test-key','restoring posts must not erase saved connection');
  page=await openPage();
  assert.equal((page.get('feed').innerHTML.match(/<article/g)||[]).length,2,'restoration survives reload');
  console.log('Hidden posts: legacy recovery, hide, undo, restore, reload, restore all, and connection preservation passed.');
})().catch(e=>{console.error(e);process.exitCode=1});

