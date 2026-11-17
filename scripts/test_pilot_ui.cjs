/* No browser/network dependency: LAN HTTP UUID + safe text/Markdown regressions. */
const assert = require('node:assert/strict');
const {webcrypto} = require('node:crypto');
const {uuid, markdown, money} = require('../apps/portal/assets/pilot.js');
const originalCrypto = globalThis.crypto;
Object.defineProperty(globalThis, 'crypto', {value:{getRandomValues:webcrypto.getRandomValues.bind(webcrypto)}, configurable:true});
const ids = Array.from({length:100},()=>uuid());
assert.equal(new Set(ids).size,100);
ids.forEach(id=>assert.match(id,/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/));
Object.defineProperty(globalThis, 'crypto', {value:originalCrypto, configurable:true});
class Node {
 constructor(tag){this.tag=tag;this.children=[];this._text='';}
 set textContent(t){this._text=String(t);}
 get textContent(){return this._text+this.children.map(c=>c.textContent).join('');}
 append(...nodes){this.children.push(...nodes);}
}
globalThis.document={createElement:tag=>new Node(tag),createTextNode:t=>{const n=new Node('#text');n.textContent=t;return n;}};
const root = new Node('div');
markdown(root,'**Paid**\n|Item|Value|\n|---|---|\n|Fee|0|\n<img src=x onerror=alert(1)>\n<script>alert(1)</script>');
function tags(n){return [n.tag,...n.children.flatMap(tags)];}
assert(tags(root).includes('table'));
assert(tags(root).includes('strong'));
assert(!tags(root).includes('img'));
assert(!tags(root).includes('script'));
assert(root.textContent.includes('<script>'));
assert.notEqual(money(null),money(0));
console.log('Pilot UI: LAN HTTP UUID, safe Markdown, HTML text-only, null/zero amounts passed');
