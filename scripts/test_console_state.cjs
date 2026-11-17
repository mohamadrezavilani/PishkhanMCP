const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
const html=fs.readFileSync(path.join(__dirname,'../templates/index.html'),'utf8');
const source=html.match(/<script>([\s\S]*?)<\/script>/)[1];
const store=new Map([['p24-session','session-a'],['p24-conversation:session-a','chat-a']]);
const sent=[];
function load(){
 const elements=new Map();
 const node=()=>({value:'',textContent:'',disabled:false,children:[],append(n){this.children.push(n)},replaceChildren(...n){this.children=n},scrollIntoView(){}});
 const el=id=>{if(id==='access-key')return null;if(!elements.has(id))elements.set(id,node());return elements.get(id)};
 const context={document:{getElementById:el,createElement:node},sessionStorage:{getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v),removeItem:k=>store.delete(k)},location:{origin:'http://local.test'},crypto:{randomUUID:()=> 'key'},setTimeout,clearTimeout,console,fetch:async(path,opts)=>({json:async()=>{
  if(path==='/api/chat/'){const data=JSON.parse(opts.body);sent.push(data);return{ok:true,session_id:data.session_id,conversation_id:data.session_id==='session-a'?'chat-a':'chat-b',reply:'Mock reply'}}
  if(path.startsWith('/api/conversations/chat-'))return{ok:true,messages:[{role:'assistant',content:'Restored history'}]};
  if(path.startsWith('/api/conversations/?'))return{ok:true,items:[{conversation_id:'chat-a',preview:'Saved',updated_at:'test'}]};
  return{tools:[],items:[],total:0};
 }})};
 vm.createContext(context);vm.runInContext(source,context);return{el,context};
}
const tick=()=>new Promise(r=>setImmediate(r));
(async()=>{
 let p=load();await tick();assert.equal(p.el('conversation-id').textContent,'chat-a');assert.equal(p.el('chatlog').children[0].textContent,'Restored history');
 p.el('chat-input').value='continue';await p.el('send-chat').onclick({target:p.el('send-chat')});assert.equal(sent.at(-1).conversation_id,'chat-a');
 p=load();await tick();assert.equal(p.el('conversation-id').textContent,'chat-a');
 p.el('session-id').value='session-b';p.el('session-id').onchange();assert.equal(p.el('conversation-id').textContent,'');
 p.el('chat-input').value='new chat';await p.el('send-chat').onclick({target:p.el('send-chat')});assert.equal(sent.at(-1).conversation_id,null);
 p.el('session-id').value='session-a';p.el('session-id').onchange();await tick();assert.equal(p.el('conversation-id').textContent,'chat-a');
 await p.el('load-conversations').onclick({target:p.el('load-conversations')});assert.equal(p.el('conversation-select').children.length,2);
 p.el('new-conversation').onclick();assert.equal(store.get('p24-conversation:session-a'),undefined);
 console.log(JSON.stringify({ok:true,checks:['restore_on_reload','persist_after_response','isolate_sessions','restore_after_switch','list_conversations','explicit_new_chat'],kind:'Node DOM stub unit test, not browser rendering'}));
})().catch(e=>{console.error(e);process.exit(1)});
