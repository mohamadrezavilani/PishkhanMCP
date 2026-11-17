/* Offline DOM and click wiring tests. No model, bank, or browser dependency. */
const assert = require('node:assert/strict');
const {webcrypto} = require('node:crypto');
const ui = require('../apps/portal/assets/pilot.js');
const originalCrypto = globalThis.crypto;
Object.defineProperty(globalThis,'crypto',{value:{getRandomValues:webcrypto.getRandomValues.bind(webcrypto)},configurable:true});
const ids=Array.from({length:100},()=>ui.uuid());
assert.equal(new Set(ids).size,100);
ids.forEach(id=>assert.match(id,/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/));
Object.defineProperty(globalThis,'crypto',{value:originalCrypto,configurable:true});
class Node {
 constructor(tag){this.tag=tag;this.children=[];this._text='';this.dataset={};this.attributes={};this.disabled=false;this.hidden=false;this.className='';this.classList={add:cls=>{this.className+=' '+cls;}};}
 set textContent(t){this._text=String(t);this.children=[];}
 get textContent(){return this._text+this.children.map(c=>c.textContent).join('');}
 append(...nodes){this.children.push(...nodes);for(const n of nodes)n.parent=this;}
 prepend(...nodes){this.children.unshift(...nodes);}
 replaceChildren(...nodes){this._text='';this.children=[];this.append(...nodes);}
 setAttribute(key,value){this.attributes[key]=value;}
 remove(){if(this.parent)this.parent.children=this.parent.children.filter(n=>n!==this);}
 focus(){}
 scrollIntoView(){}
 click(){if(!this.disabled)return this.onclick?.();}
}
const nodes=new Map();
globalThis.document={
 body:new Node('body'),getElementById:id=>{if(!nodes.has(id)){const n=new Node('div');n.id=id;nodes.set(id,n);}return nodes.get(id);},
 createElement:tag=>new Node(tag),createTextNode:t=>{const n=new Node('#text');n.textContent=t;return n;},
 querySelector:()=>({value:'synthetic-csrf'}),querySelectorAll:()=>[]
};
function tags(n){return [n.tag,...n.children.flatMap(tags)];}
function find(n,test){if(test(n))return n;for(const child of n.children){const found=find(child,test);if(found)return found;}}
const root=new Node('div');
ui.markdown(root,'**Paid**\n|Item|Value|\n|---|---|\n|Fee|0|\n<img src=x onerror=alert(1)>\n<script>alert(1)</script>');
assert(tags(root).includes('table'));assert(tags(root).includes('strong'));assert(!tags(root).includes('img'));assert(!tags(root).includes('script'));assert(root.textContent.includes('<script>'));assert.notEqual(ui.money(null),ui.money(0));
const link=new Node('div');
ui.markdown(link,'**[Pay bill]\\([https://bank.example/pay](https://bank.example/pay))**');
assert.equal(link.textContent,'Pay bill');assert(!tags(link).includes('a'));
assert.equal(ui.safeUrl('https://user:secret@bank.example/pay'),null);assert.equal(ui.safeUrl('javascript:alert(1)'),null);
const card={payment_key:'synthetic-key',payment_status:'Unpaid',bill_ids:['bill'],amount:92000,fee:0,total_amount:92000,requires_user_action:true,payment_complete:false,redirect_url:'https://bank.example/pay'};
const fakeState=paid=>({ok:true,mode:'live',authenticated:true,account:{state:'authenticated',phone:'09120000000'},usage:{used:1,limit:50,remaining:49},busy:false,conversations:[],bills:[],payments:[{...card,...(paid?{payment_status:'Paid',payment_complete:true,requires_user_action:false,redirect_url:null}:{})}],auto_payment_links:true});
(async()=>{
 ui.renderState({...fakeState(false),authenticated:false,account:{state:'guest',phone:''},payments:[]});
 assert.equal(document.body.dataset.auth,'guest');assert.equal(nodes.get('composer-area').hidden,true);
 ui.renderState(fakeState(false));assert.equal(document.body.dataset.auth,'signed-in');assert.equal(nodes.get('member').hidden,false);assert.equal(nodes.get('user-phone').textContent,'09120000000');
 assert.equal(nodes.get('composer-area').hidden,false);
 let requests=[];
 globalThis.fetch=async(path,opts)=>{requests.push({path,body:JSON.parse(opts.body)});return {ok:true,json:async()=>({...fakeState(false),payment_update:{payment_key:'synthetic-key',message:'Unchanged status received',checked_at:'2026-11-17T10:00:00Z'}})};};
 const button=find(nodes.get('payments'),n=>n.className.includes('payment-status-action'));
 assert(button,'Status action must be a real wired button');await button.click();
 assert.deepEqual(requests[0],{path:'/api/portal/payment/',body:{action:'status',payment_key:'synthetic-key'}});
 assert(nodes.get('chat-payments').textContent.includes('Unchanged status received'));
 assert(nodes.get('alert').textContent.includes('Unchanged status received'));
 assert(tags(nodes.get('chat-payments')).includes('a'),'Unpaid bank action remains available');
 globalThis.fetch=async()=>({ok:true,json:async()=>({...fakeState(true),payment_update:{payment_key:'synthetic-key',message:'Payment confirmed',checked_at:'2026-11-17T10:01:00Z',payment_complete:true}})});
 await find(nodes.get('chat-payments'),n=>n.className.includes('payment-status-action')).click();
 assert(nodes.get('chat-payments').textContent.includes('Payment confirmed'));
 assert(!tags(nodes.get('chat-payments')).includes('a'),'Paid card must not offer another payment');
 globalThis.fetch=async()=>({ok:false,status:400,json:async()=>({ok:false,error:{code:'UPSTREAM_TIMEOUT',message:'Status lookup timed out'}})});
 await find(nodes.get('chat-payments'),n=>n.className.includes('payment-status-action')).click();
 assert(nodes.get('chat-payments').textContent.includes('Status lookup timed out'));
 assert(nodes.get('alert').className.includes('error'));
 assert(!find(nodes.get('chat-payments'),n=>n.className.includes('payment-status-action')).disabled);
 console.log('Pilot UI: guest/member, nested Markdown, structured IPG card, status click/unchanged/Paid/error and zero-vs-null passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
