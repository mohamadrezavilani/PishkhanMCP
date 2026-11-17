/* Consumer pilot UI. DOM text nodes only; no model-generated HTML execution. */
(() => {
'use strict';
const words = {
 title:'دستیار پیشخوان', subtitle:'نسخهٔ آزمایشی شبکهٔ داخلی', connect:'ورود به پیشخوان', logout:'خروج', newChat:'گفت‌وگوی جدید', conversations:'گفت‌وگوهای من', pilotScope:'یک مسیر ساده‌تر برای قبض‌ها', pilotNote:'فعلاً قبض موبایل، برق و آب را با هم تست می‌کنیم. بازخورد شما مسیر نسخهٔ بعدی را مشخص می‌کند.', feedback:'ثبت بازخورد', workspace:'فضای شخصی شما', readyTitle:'چه کاری برایتان انجام بدهم؟', notConnected:'حساب متصل نیست', welcome:'خوش آمدید.', intro:'به زبان خودتان بنویسید. قبض را استعلام کنید، لینک درگاه بگیرید و نتیجهٔ پرداخت را همین‌جا ببینید.', mobile:'قبض موبایل', mobileHint:'همراه اول، ایرانسل و رایتل', electricity:'قبض برق', electricityHint:'با شناسهٔ قبض', water:'قبض آب', waterHint:'استعلام و پیگیری', working:'در حال بررسی درخواست شما…', message:'پیام شما', placeholder:'مثلاً: قبض همراه اولم را بررسی کن…', send:'ارسال', composerNote:'پرداخت نهایی فقط با اقدام شما در صفحهٔ بانک انجام می‌شود.', records:'سوابق همین حساب', billsAndPayments:'قبض‌ها و پرداخت‌ها', refresh:'بازخوانی سوابق', recordsNote:'این بخش نتایج ذخیره‌شده را نشان می‌دهد؛ بازخوانی سوابق، استعلام تازه نیست.', emptyRecords:'هنوز قبض یا پرداختی در این حساب نمایش داده نشده است.', footer:'پایلوت داخلی • نسخهٔ عمومی نیست', account:'اتصال حساب', loginTitle:'ورود به پیشخوان', loginNote:'شمارهٔ حساب خودتان را وارد کنید. کد ورود برای همین شماره ارسال می‌شود.', phone:'شمارهٔ موبایل', otp:'کد ورود', sendOtp:'دریافت کد ورود', verifyOtp:'تأیید ورود', changePhone:'اصلاح شماره / ارسال مجدد', demoOtp:'حالت نمایشی: کد ورود ۱۲۳۴۵۶ است؛ پیامکی ارسال نمی‌شود.', pilotExperience:'تجربهٔ شما', feedbackTitle:'چطور بود؟', rating:'امتیاز از ۵', comment:'چه چیزی بهتر شود؟', submitFeedback:'ثبت نظر', thanks:'ممنون؛ بازخورد شما ثبت شد.', you:'شما', live:'اتصال واقعی', demo:'نمایشی', connected:'حساب متصل', steps:'مراحل انجام‌شده', paid:'پرداخت تأیید شد', unpaid:'پرداخت‌نشده', pending:'نیازمند بررسی', link:'دریافت لینک درگاه', bank:'رفتن به درگاه', status:'بررسی وضعیت پرداخت', toman:'تومان', unknown:'اعلام نشده', fee:'کارمزد', observed:'آخرین بررسی', final:'پایان‌دوره', interim:'میان‌دوره', saved:'نتیجهٔ ذخیره‌شده', budget:'پیام باقی‌مانده برای کل پایلوت در امروز', network:'ارتباط قطع شد. پیام خودکار تکرار نمی‌شود؛ صفحه را بازخوانی کنید تا نتیجه بازیابی شود.', busyNotice:'درخواست قبلی هنوز در حال اجراست. آن را دوباره نفرستید.', limit:'سهمیهٔ گفت‌وگوی امروز پایان یافته است. پیگیری پرداخت همچنان فعال است.', mci:'همراه اول', irancell:'ایرانسل', rightel:'رایتل', confirmLink:'لینک پرداخت این قبض ساخته شود؟ مبلغ نهایی و کارمزد پس از پاسخ پیشخوان نمایش داده می‌شود.', demoWarning:'حالت نمایشی است؛ نتایج واقعی نیستند.'
};

Object.assign(words, {
  "live": "\u062e\u062f\u0645\u0627\u062a \u067e\u06cc\u0634\u062e\u0648\u0627\u0646",
  "notConnected": "\u0648\u0627\u0631\u062f \u062d\u0633\u0627\u0628 \u0646\u0634\u062f\u0647\u200c\u0627\u06cc\u062f",
  "signedIn": "\u0648\u0627\u0631\u062f \u0634\u062f\u0647\u200c\u0627\u06cc\u062f",
  "guestHeading": "\u0642\u0628\u0636\u200c\u0647\u0627\u06cc\u062a\u0627\u0646 \u0631\u0627 \u0633\u0627\u062f\u0647\u200c\u062a\u0631 \u0645\u062f\u06cc\u0631\u06cc\u062a \u06a9\u0646\u06cc\u062f",
  "guestTitle": "\u0634\u0631\u0648\u0639 \u06cc\u06a9 \u062a\u062c\u0631\u0628\u0647\u0654 \u0633\u0627\u062f\u0647\u200c\u062a\u0631",
  "guestIntro": "\u0628\u0627 \u0634\u0645\u0627\u0631\u0647\u0654 \u0645\u0648\u0628\u0627\u06cc\u0644 \u062e\u0648\u062f \u0648\u0627\u0631\u062f \u0634\u0648\u06cc\u062f. \u0642\u0628\u0636 \u0631\u0627 \u062f\u0631 \u06af\u0641\u062a\u200c\u0648\u06af\u0648 \u0628\u0628\u06cc\u0646\u06cc\u062f \u0648 \u0627\u0632 \u0647\u0645\u06cc\u0646\u200c\u062c\u0627 \u0628\u0647 \u062f\u0631\u06af\u0627\u0647 \u067e\u0631\u062f\u0627\u062e\u062a \u0628\u0631\u0648\u06cc\u062f.",
  "startLogin": "\u0648\u0631\u0648\u062f \u0628\u0627 \u0634\u0645\u0627\u0631\u0647\u0654 \u0645\u0648\u0628\u0627\u06cc\u0644",
  "loginSteps": "\u06f1. \u0634\u0645\u0627\u0631\u0647\u0654 \u0645\u0648\u0628\u0627\u06cc\u0644   \u2190   \u06f2. \u06a9\u062f \u0648\u0631\u0648\u062f   \u2190   \u06f3. \u06af\u0641\u062a\u200c\u0648\u06af\u0648",
  "welcomeBack": "\u0633\u0644\u0627\u0645\u060c \u062e\u0648\u0634 \u0622\u0645\u062f\u06cc\u062f",
  "intro": "\u0642\u0628\u0636 \u0645\u0648\u0631\u062f\u0646\u0638\u0631\u062a\u0627\u0646 \u0631\u0627 \u0628\u06af\u0648\u06cc\u06cc\u062f\u061b \u0645\u0628\u0644\u063a \u0648 \u0644\u06cc\u0646\u06a9 \u067e\u0631\u062f\u0627\u062e\u062a\u060c \u06a9\u0646\u0627\u0631 \u0647\u0645 \u0646\u0645\u0627\u06cc\u0634 \u062f\u0627\u062f\u0647 \u0645\u06cc\u200c\u0634\u0648\u0646\u062f.",
  "guestHistory": "\u0628\u0631\u0627\u06cc \u062f\u06cc\u062f\u0646 \u06af\u0641\u062a\u200c\u0648\u06af\u0648\u0647\u0627 \u0648\u0627\u0631\u062f \u0634\u0648\u06cc\u062f.",
  "noChats": "\u0627\u0648\u0644\u06cc\u0646 \u06af\u0641\u062a\u200c\u0648\u06af\u0648\u06cc \u0634\u0645\u0627 \u0627\u0632 \u0627\u06cc\u0646\u062c\u0627 \u0634\u0631\u0648\u0639 \u0645\u06cc\u200c\u0634\u0648\u062f.",
  "waitingOtp": "\u0645\u0646\u062a\u0638\u0631 \u062a\u0623\u06cc\u06cc\u062f \u06a9\u062f \u0648\u0631\u0648\u062f",
  "stepOne": "\u0645\u0631\u062d\u0644\u0647\u0654 \u06f1 \u0627\u0632 \u06f2 \u00b7 \u0634\u0645\u0627\u0631\u0647\u0654 \u0645\u0648\u0628\u0627\u06cc\u0644",
  "stepTwo": "\u0645\u0631\u062d\u0644\u0647\u0654 \u06f2 \u0627\u0632 \u06f2 \u00b7 \u062a\u0623\u06cc\u06cc\u062f \u0634\u0645\u0627\u0631\u0647",
  "otpSent": "\u06a9\u062f \u067e\u06cc\u0627\u0645\u06a9\u200c\u0634\u062f\u0647 \u0628\u0647 \u0634\u0645\u0627\u0631\u0647\u0654 \u0632\u06cc\u0631 \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f.",
  "sendingOtp": "\u062f\u0631 \u062d\u0627\u0644 \u0627\u0631\u0633\u0627\u0644 \u06a9\u062f\u2026",
  "verifyingOtp": "\u062f\u0631 \u062d\u0627\u0644 \u062a\u0623\u06cc\u06cc\u062f \u0648\u0631\u0648\u062f\u2026",
  "loginSuccess": "\u062e\u0648\u0634 \u0622\u0645\u062f\u06cc\u062f\u061b \u062d\u0633\u0627\u0628 \u0634\u0645\u0627 \u0622\u0645\u0627\u062f\u0647\u0654 \u0627\u0633\u062a\u0641\u0627\u062f\u0647 \u0627\u0633\u062a.",
  "mobileExample": "\u0642\u0628\u0636 \u0647\u0645\u0631\u0627\u0647 \u0627\u0648\u0644\u0645 \u0631\u0627 \u0628\u0631\u0631\u0633\u06cc \u06a9\u0646.",
  "electricityExample": "\u0642\u0628\u0636 \u0628\u0631\u0642\u0645 \u0631\u0627 \u0628\u0631\u0631\u0633\u06cc \u06a9\u0646.",
  "waterExample": "\u0642\u0628\u0636 \u0622\u0628\u0645 \u0631\u0627 \u0628\u0631\u0631\u0633\u06cc \u06a9\u0646.",
  "linkInCard": "\u0644\u06cc\u0646\u06a9 \u062f\u0631 \u06a9\u0627\u0631\u062a \u067e\u0631\u062f\u0627\u062e\u062a",
  "billPayment": "\u067e\u0631\u062f\u0627\u062e\u062a \u0642\u0628\u0636",
  "billAmount": "\u0645\u0628\u0644\u063a \u0642\u0628\u0636",
  "checkingPayment": "\u062f\u0631 \u062d\u0627\u0644 \u062f\u0631\u06cc\u0627\u0641\u062a \u0648\u0636\u0639\u06cc\u062a\u2026",
  "preparingLink": "\u062f\u0631 \u062d\u0627\u0644 \u0622\u0645\u0627\u062f\u0647\u200c\u0633\u0627\u0632\u06cc \u0644\u06cc\u0646\u06a9\u2026",
  "lastChecked": "\u0622\u062e\u0631\u06cc\u0646 \u062f\u0631\u06cc\u0627\u0641\u062a \u0648\u0636\u0639\u06cc\u062a",
  "statusReceived": "\u0648\u0636\u0639\u06cc\u062a \u0627\u0632 \u067e\u06cc\u0634\u062e\u0648\u0627\u0646 \u062f\u0631\u06cc\u0627\u0641\u062a \u0634\u062f.",
  "paymentDone": "\u067e\u0631\u062f\u0627\u062e\u062a \u062a\u0623\u06cc\u06cc\u062f \u0634\u062f\u0647 \u0627\u0633\u062a\u061b \u0646\u06cc\u0627\u0632\u06cc \u0628\u0647 \u067e\u0631\u062f\u0627\u062e\u062a \u062f\u0648\u0628\u0627\u0631\u0647 \u0646\u06cc\u0633\u062a.",
  "paymentReady": "\u0644\u06cc\u0646\u06a9 \u0622\u0645\u0627\u062f\u0647 \u0627\u0633\u062a. \u067e\u0631\u062f\u0627\u062e\u062a \u0646\u0647\u0627\u06cc\u06cc \u062f\u0631 \u0635\u0641\u062d\u0647\u0654 \u0628\u0627\u0646\u06a9 \u0627\u0646\u062c\u0627\u0645 \u0645\u06cc\u200c\u0634\u0648\u062f.",
  "paymentPending": "\u0646\u062a\u06cc\u062c\u0647 \u0647\u0646\u0648\u0632 \u0642\u0637\u0639\u06cc \u0646\u06cc\u0633\u062a\u061b \u0648\u0636\u0639\u06cc\u062a \u0647\u0645\u06cc\u0646 \u067e\u0631\u062f\u0627\u062e\u062a \u0631\u0627 \u0628\u0631\u0631\u0633\u06cc \u06a9\u0646\u06cc\u062f.",
  "bank": "\u067e\u0631\u062f\u0627\u062e\u062a \u062f\u0631 \u062f\u0631\u06af\u0627\u0647 \u0628\u0627\u0646\u06a9\u06cc \u2197",
  "status": "\u067e\u0631\u062f\u0627\u062e\u062a \u06a9\u0631\u062f\u0645\u061b \u0628\u0631\u0631\u0633\u06cc \u0648\u0636\u0639\u06cc\u062a",
  "autoLink": "\u0644\u06cc\u0646\u06a9 \u067e\u0631\u062f\u0627\u062e\u062a \u0628\u0639\u062f \u0627\u0632 \u0627\u0633\u062a\u0639\u0644\u0627\u0645 \u0622\u0645\u0627\u062f\u0647 \u0634\u0648\u062f",
  "autoLinkHint": "\u0641\u0642\u0637 \u0644\u06cc\u0646\u06a9 \u0633\u0627\u062e\u062a\u0647 \u0645\u06cc\u200c\u0634\u0648\u062f\u061b \u0647\u06cc\u0686 \u0645\u0628\u0644\u063a\u06cc \u062e\u0648\u062f\u06a9\u0627\u0631 \u067e\u0631\u062f\u0627\u062e\u062a \u0646\u0645\u06cc\u200c\u0634\u0648\u062f.",
  "focusTitle": "\u06a9\u0627\u0631\u062a \u067e\u0631\u062f\u0627\u062e\u062a \u0634\u0645\u0627",
  "recordsUpdated": "\u0633\u0648\u0627\u0628\u0642 \u0630\u062e\u06cc\u0631\u0647\u200c\u0634\u062f\u0647 \u0628\u0627\u0632\u062e\u0648\u0627\u0646\u06cc \u0634\u062f\u0646\u062f.",
  "inquiryResult": "\u062f\u0631\u06cc\u0627\u0641\u062a \u0646\u062a\u06cc\u062c\u0647\u0654 \u0627\u0633\u062a\u0639\u0644\u0627\u0645",
  "beginRequest": "\u062b\u0628\u062a \u062f\u0631\u062e\u0648\u0627\u0633\u062a",
  "checkingService": "\u0628\u0631\u0631\u0633\u06cc \u062e\u062f\u0645\u062a",
  "accountLabel": "\u062d\u0633\u0627\u0628 \u067e\u06cc\u0634\u062e\u0648\u0627\u0646 \u0634\u0645\u0627",
  "guestScope": "\u0642\u0628\u0636 \u0645\u0648\u0628\u0627\u06cc\u0644\u060c \u0628\u0631\u0642 \u0648 \u0622\u0628",
  "loginNote": "\u0634\u0645\u0627\u0631\u0647\u0654 \u062d\u0633\u0627\u0628 \u067e\u06cc\u0634\u062e\u0648\u0627\u0646 \u062e\u0648\u062f \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f. \u06a9\u062f \u0648\u0631\u0648\u062f \u0628\u0631\u0627\u06cc \u0647\u0645\u06cc\u0646 \u0634\u0645\u0627\u0631\u0647 \u0627\u0631\u0633\u0627\u0644 \u0645\u06cc\u200c\u0634\u0648\u062f."
});
const t = k => words[k] || k;
const $ = id => document.getElementById(id);
const num = v => new Intl.NumberFormat('fa-IR',{maximumFractionDigits:1}).format(v);
const money = v => typeof v === 'number' && Number.isFinite(v) ? num(v/10)+' '+t('toman') : t('unknown');
const date = v => {if(!v)return '';try{return new Intl.DateTimeFormat('fa-IR',{dateStyle:'short',timeStyle:'short'}).format(new Date(v));}catch{return '';}};
const text = (tag,value,cls) => {const n=document.createElement(tag);n.textContent=value;if(cls)n.className=cls;return n;};
let snapshot=null, conversation=null, busy=false, otpStage=false, ticker=null, initializedAuto=false;
const focusedPayments=new Set(), pendingPayments=new Set(), paymentMessages=new Map();
const store={get:k=>{try{return sessionStorage.getItem(k);}catch{return null;}},set:(k,v)=>{try{v?sessionStorage.setItem(k,v):sessionStorage.removeItem(k);}catch{}}};
function uuid(){if(globalThis.crypto?.randomUUID)return crypto.randomUUID();const b=new Uint8Array(16);crypto.getRandomValues(b);b[6]=(b[6]&15)|64;b[8]=(b[8]&63)|128;const s=[...b].map(v=>v.toString(16).padStart(2,'0')).join('');return `${s.slice(0,8)}-${s.slice(8,12)}-${s.slice(12,16)}-${s.slice(16,20)}-${s.slice(20)}`;}
function csrf(){return document.querySelector('[name=csrfmiddlewaretoken]').value;}
async function api(path,body){
  let response;
  try{response=await fetch('/api/portal/'+path,{method:body?'POST':'GET',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRFToken':csrf()},...(body?{body:JSON.stringify(body)}:{})});}
  catch{throw new Error(t('network'));}
  let value;try{value=await response.json();}catch{throw new Error('HTTP '+response.status);}
  if(!response.ok||value.ok===false){const e=new Error(value.error?.message||value.reply||'HTTP '+response.status);e.payload=value;e.code=value.error?.code;throw e;}return value;
}
function notify(message,error=false,success=false){const n=$('alert');n.hidden=!message;n.textContent=message||'';n.className='alert'+(error?' error':success?' success':'');}
function lock(value){busy=value;$('busy').hidden=!value;for(const id of ['send','new-chat','logout','connect'])$(id).disabled=value;if(ticker)clearInterval(ticker);if(value){let seconds=0;$('elapsed').textContent='';ticker=setInterval(()=>{$('elapsed').textContent=num(++seconds)+' s';},1000);}renderRecords();}
function safeUrl(value){try{const u=new URL(value);return u.protocol==='https:'&&!u.username&&!u.password?u.href:null;}catch{return null;}}
function normalizeLinks(s){
  return String(s).replace(/\\([()\[\]])/g,'$1').replace(/\[(https?:\/\/[^\s\]]+)\]\((https?:\/\/[^\s)]+)\)/g,(_,label,url)=>label===url?url:label);
}
// Model links are labels only. Only structured, account-owned cards can navigate.
function inline(parent,source){
  const s=normalizeLinks(source), re=/(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^\s)]+\)|https?:\/\/[^\s)]+)/g;
  let at=0,m;
  while((m=re.exec(s))){
    parent.append(document.createTextNode(s.slice(at,m.index)));const token=m[0];
    if(token.startsWith('**')){const strong=document.createElement('strong');inline(strong,token.slice(2,-2));parent.append(strong);}
    else if(token.startsWith('`'))parent.append(text('code',token.slice(1,-1)));
    else if(token.startsWith('['))parent.append(text('span',token.slice(1,token.indexOf('](')),'inline-reference'));
    else parent.append(text('span',t('linkInCard'),'inline-reference'));
    at=re.lastIndex;
  }
  parent.append(document.createTextNode(s.slice(at)));
}
function markdown(parent,content){const lines=String(content).split('\n');for(let i=0;i<lines.length;i++){const line=lines[i];if(line.trim().startsWith('|')&&i+1<lines.length&&/^\s*\|?[\s:|\-]+\|\s*$/.test(lines[i+1])){const wrap=text('div','','table-wrap'),table=document.createElement('table');let row=0;while(i<lines.length&&lines[i].trim().startsWith('|')){if(row!==1){const tr=document.createElement('tr');for(const cell of lines[i].trim().replace(/^\||\|$/g,'').split('|')){const td=document.createElement(row===0?'th':'td');inline(td,cell.trim());tr.append(td);}table.append(tr);}row++;i++;}i--;wrap.append(table);parent.append(wrap);}else if(line.trim()&&line.trim()!=='---'){const p=document.createElement('p');inline(p,line.replace(/^#{1,4}\s+/,''));parent.append(p);}}}
function login(){otpStage=snapshot?.account.state==='otp_pending';$('phone').value=snapshot?.account.phone||'';updateLogin();$('login-error').textContent='';$('login-dialog').showModal();(otpStage?$('otp'):$('phone')).focus();}
function updateLogin(){
  $('otp-row').hidden=!otpStage;$('phone').readOnly=otpStage;$('otp').required=otpStage;$('change-phone').hidden=!otpStage;
  $('login-submit').textContent=t(otpStage?'verifyOtp':'sendOtp');$('login-step').textContent=t(otpStage?'stepTwo':'stepOne');
  $('login-note').textContent=t(otpStage?'otpSent':'loginNote');$('demo-note').hidden=snapshot?.mode!=='demo';
}
function welcome(){
  const root=text('div','','welcome');root.id='welcome';const signed=!!snapshot?.authenticated;
  root.append(text('span',signed?'\u2726':'\u25c8','spark'),text('h2',t(signed?'welcomeBack':'guestTitle')),text('p',t(signed?'intro':'guestIntro')));
  if(!signed){const c=button(t('startLogin'),login);c.className='primary guest-cta';root.append(c,text('div',t('loginSteps'),'login-steps'));}
  const examples=text('div','','suggestions');
  for(const kind of ['mobile','electricity','water']){const b=button('',()=>{if(!snapshot?.authenticated){login();return;}$('message').value=t(kind+'Example');$('message').focus();});b.append(text('span',kind==='mobile'?'\u260e':kind==='electricity'?'\u26a1':'\u25ce','icon'),text('strong',t(kind)),text('small',t(kind+'Hint')));examples.append(b);}
  root.append(examples);$('chatlog').append(root);
}
function resetChat(){ $('chatlog').replaceChildren();focusedPayments.clear();welcome();renderRecords(); }
function activityLabel(n){return ({p24_mobile_bill:t('mobile'),p24_electricity_bill:t('electricity'),p24_water_bill:t('water'),p24_recent_bills:t('records'),p24_bill_payment_link:t('link'),p24_payment_status:t('status'),p24_run_inquiry:t('inquiryResult'),p24_begin_request:t('beginRequest')})[n]||t('checkingService');}
function addMessage(role,content,activity){$('welcome')?.remove();const div=text('article','','message '+role);div.append(text('div',role==='user'?t('you'):t('title'),'byline'));const bubble=text('div','','bubble');markdown(bubble,content);div.append(bubble);if(activity?.length){const details=document.createElement('details');details.className='activity';details.append(text('summary',t('steps')+' ('+num(activity.length)+')'));for(const item of activity)details.append(text('div',(item.ok?'\u2713 ':'! ')+activityLabel(item.name)+(item.error_code?' / '+item.error_code:'')));div.append(details);}$('chatlog').append(div);$('chatlog').scrollTop=$('chatlog').scrollHeight;}
function setConversation(id){conversation=id||null;store.set('p24-portal-conversation',conversation);}
function includeCards(r){for(const key of r.payment_keys||[])focusedPayments.add(key);if(snapshot&&r.payment_cards){const updated=new Map(snapshot.payments.map(p=>[p.payment_key,p]));for(const p of r.payment_cards)updated.set(p.payment_key,p);snapshot.payments=[...updated.values()];}renderRecords();}
async function restore(id){if(busy)return;try{const r=await api('history/'+encodeURIComponent(id)+'/');setConversation(r.conversation_id);$('chatlog').replaceChildren();focusedPayments.clear();for(const m of r.messages)addMessage(m.role,m.content);if(!r.messages.length)welcome();includeCards(r);renderNav();}catch(e){if(e.code==='CONVERSATION_NOT_FOUND')setConversation(null);else notify(e.message,true);}}
function renderNav(){$('conversations').replaceChildren();for(const c of snapshot?.conversations||[]){const b=text('button',c.title||t('newChat'),'conv'+(c.id===conversation?' active':''));b.append(text('span',date(c.updated_at),'conv-date'));b.onclick=()=>restore(c.id);$('conversations').append(b);}$('history-empty').hidden=!!snapshot?.conversations.length;$('history-empty').textContent=t(snapshot?.authenticated?'noChats':'guestHistory');}
function button(label,action){const b=text('button',label,'quiet');b.type='button';b.onclick=action;return b;}
function record(title,amount,paid,status){const card=text('article','','record');const h=text('div','','record-head');h.append(text('span',title,'record-title'),text('span',paid?t('paid'):status==='Unpaid'?t('unpaid'):t('pending'),'status'+(paid?' success':'')));card.append(h,text('div',money(amount),'record-amount'));return card;}
function paymentCard(p,onStatus){
  const related=(snapshot?.bills||[]).filter(b=>(p.bill_ids||[]).includes(b.bill_id));
  const title=related.length===1?t(related[0].service_id):t('billPayment');
  const card=record(title,p.total_amount,p.payment_complete,p.payment_status);card.classList.add('payment-card');card.dataset.paymentKey=p.payment_key;
  const meta=text('div','','payment-subject');if(related[0]?.line_number){const phone=text('bdi',related[0].line_number);phone.dir='ltr';meta.append(phone);}if(related.length===1&&typeof related[0].final_term==='boolean')meta.append(text('span',t(related[0].final_term?'final':'interim')));card.prepend(meta);
  const breakdown=text('dl','','payment-breakdown');for(const [label,value] of [[t('billAmount'),p.amount],[t('fee'),p.fee]])breakdown.append(text('dt',label),text('dd',money(value)));card.append(breakdown);
  card.append(text('p',t(p.payment_complete?'paymentDone':p.requires_user_action?'paymentReady':'paymentPending'),'payment-explainer'));
  const actions=text('div','','record-actions');const url=safeUrl(p.redirect_url);
  if(url&&p.requires_user_action&&!p.payment_complete&&!p.payment_confirmed){const a=text('a',t('bank'),'primary bank-action');a.href=url;a.target='_blank';a.rel='noopener noreferrer';a.setAttribute('aria-label',t('bank')+' - '+title);actions.append(a);}
  const b=button(t(pendingPayments.has(p.payment_key)?'checkingPayment':'status'),()=>onStatus(p.payment_key));b.classList.add('payment-status-action');b.disabled=busy||!!snapshot?.busy||pendingPayments.has(p.payment_key);b.setAttribute('aria-busy',String(pendingPayments.has(p.payment_key)));actions.append(b);card.append(actions);
  const note=paymentMessages.get(p.payment_key);const feedback=text('div',note?.message||'', 'payment-result'+(note?.error?' error':p.payment_complete?' success':''));feedback.setAttribute('role','status');feedback.setAttribute('aria-live','polite');feedback.hidden=!note;card.append(feedback);
  const checked=note?.checked_at||p.last_checked_at;if(checked)card.append(text('div',t('lastChecked')+': '+date(checked),'record-meta checked-at'));
  return card;
}
async function payment(action,args){
  if(busy||snapshot?.busy){notify(t('busyNotice'));return;}
  const key=args.payment_key||'bill:'+args.bill_ids.join(',');if(pendingPayments.has(key))return;
  pendingPayments.add(key);paymentMessages.delete(key);renderRecords();notify(t(action==='status'?'checkingPayment':'preparingLink'));
  try{
    const s=await api('payment/',{action,...args});const u=s.payment_update;
    if(u?.payment_key){focusedPayments.add(u.payment_key);paymentMessages.set(u.payment_key,u);}
    renderState(s);notify(u?.message||t('statusReceived'),false,true);
    const shown=[...document.querySelectorAll('.payment-card')].find(n=>n.dataset.paymentKey===u?.payment_key);shown?.scrollIntoView({block:'nearest',behavior:'smooth'});
  }catch(e){paymentMessages.set(key,{message:e.message,error:true});notify(e.message,true);}
  finally{pendingPayments.delete(key);renderRecords();}
}
function renderRecords(){
  if(!snapshot)return;const ps=$('payments'),bs=$('bills'),focus=$('chat-payments');ps.replaceChildren();bs.replaceChildren();focus.replaceChildren();
  for(const p of snapshot.payments){const c=paymentCard(p,key=>payment('status',{payment_key:key}));(focusedPayments.has(p.payment_key)?focus:ps).append(c);}
  $('payment-focus').hidden=!focus.children.length;
  for(const b of snapshot.bills){
    if(b.payment_key&&snapshot.payments.some(p=>p.payment_key===b.payment_key))continue;
    const c=record(t(b.service_id),b.amount,b.payment_complete||['Paid','Settle'].includes(b.current_payment_status||b.payment_status),b.current_payment_status||b.payment_status);
    c.append(text('div',[b.line_number,b.final_term===true?t('final'):b.final_term===false?t('interim'):''].filter(Boolean).join(' / '),'record-meta'),text('div',t('saved')+' / '+date(b.observed_at),'record-meta'));
    if(!b.payment_key&&b.payment_status==='Unpaid'&&b.amount>0&&snapshot.mode==='live'){const actions=text('div','','record-actions');const btn=button(t('link'),()=>payment('link',{bill_ids:[b.bill_id]}));btn.disabled=busy||pendingPayments.has('bill:'+b.bill_id);actions.append(btn);c.append(actions);}bs.append(c);
  }
  $('empty-records').hidden=!!(snapshot.payments.length||snapshot.bills.length);
}
function renderState(s){
  const was=snapshot?.authenticated;snapshot=s;document.body.dataset.auth=s.authenticated?'signed-in':'guest';
  $('mode').className='pill '+s.mode;$('mode').textContent=t(s.mode);
  $('connect').hidden=s.authenticated;$('logout').hidden=!s.authenticated;$('member').hidden=!s.authenticated;$('user-phone').textContent=s.account.phone||'';
  $('account-state').textContent=t(s.authenticated?'signedIn':s.account.state==='otp_pending'?'waitingOtp':'notConnected');$('account-state').className='account-state '+(s.authenticated?'signed-in':'guest');
  $('chat-title').textContent=t(s.authenticated?'readyTitle':'guestHeading');$('composer-area').hidden=!s.authenticated;$('records-section').hidden=!s.authenticated;
  $('budget').textContent=num(s.usage.remaining)+' / '+num(s.usage.limit)+' '+t('budget');
  if(!initializedAuto){$('auto-link').checked=s.auto_payment_links!==false;initializedAuto=true;}
  renderNav();if(was!==s.authenticated||!$('chatlog').children.length)resetChat();renderRecords();
  if(s.mode==='demo')notify(t('demoWarning'));if(s.busy)notify(t('busyNotice'));if(s.usage.remaining===0&&s.authenticated)notify(t('limit'));
}
async function refresh(){const s=await api('state/');renderState(s);return s;}
async function recoverPending(){const key=store.get('p24-portal-pending');if(!key)return;try{const r=await api('turns/'+key+'/');if(r.state==='running'){notify(t('busyNotice'));return;}store.set('p24-portal-pending',null);if(r.result?.conversation_id){setConversation(r.result.conversation_id);await restore(conversation);}}catch(e){if(e.code==='TURN_NOT_FOUND')store.set('p24-portal-pending',null);else notify(e.message,true);}}
async function sendMessage(event){
  event.preventDefault();if(busy)return;if(!snapshot?.authenticated){login();return;}const message=$('message').value.trim();if(!message)return;if(snapshot.usage.remaining===0){notify(t('limit'));return;}
  const client_key=uuid();store.set('p24-portal-pending',client_key);addMessage('user',message);$('message').value='';notify('');lock(true);
  try{const r=await api('chat/',{message,conversation_id:conversation,client_key,auto_payment_link:$('auto-link').checked});setConversation(r.conversation_id);addMessage('assistant',r.reply||'',r.activity);includeCards(r);for(const notice of r.notices||[])notify(notice.message);store.set('p24-portal-pending',null);}
  catch(e){const r=e.payload;if(r?.conversation_id)setConversation(r.conversation_id);addMessage('assistant',r?.reply||e.message,r?.activity);if(r)includeCards(r);notify(e.message,true);if(r&&e.code!=='TURN_RUNNING')store.set('p24-portal-pending',null);}
  finally{lock(false);try{await refresh();}catch(e){notify(e.message,true);}}
}
function init(){
  for(const n of document.querySelectorAll('[data-i18n]'))n.textContent=t(n.dataset.i18n);for(const n of document.querySelectorAll('[data-placeholder]'))n.placeholder=t(n.dataset.placeholder);document.title=t('title');
  $('connect').onclick=login;$('login-close').onclick=()=>$('login-dialog').close();$('change-phone').onclick=()=>{otpStage=false;updateLogin();$('phone').focus();};
  $('login-form').onsubmit=async e=>{e.preventDefault();const b=$('login-submit');b.disabled=true;b.textContent=t(otpStage?'verifyingOtp':'sendingOtp');$('login-error').textContent='';try{if(!otpStage){const r=await api('otp/send/',{phone:$('phone').value});otpStage=true;updateLogin();$('phone').value=r.phone;$('otp').focus();}else{const s=await api('otp/verify/',{otp:$('otp').value});$('otp').value='';$('login-dialog').close();setConversation(null);renderState(s);notify(t('loginSuccess'),false,true);}}catch(err){$('login-error').textContent=err.message;}finally{b.disabled=false;updateLogin();}};
  $('logout').onclick=async()=>{try{await api('logout/',{});setConversation(null);store.set('p24-portal-pending',null);location.reload();}catch(e){notify(e.message,true);}};
  $('new-chat').onclick=()=>{if(busy)return;if(!snapshot?.authenticated){login();return;}setConversation(null);resetChat();renderNav();$('message').focus();};
  $('refresh').onclick=async()=>{try{await refresh();await recoverPending();notify(t('recordsUpdated'),false,true);}catch(e){notify(e.message,true);}};
  $('chat-form').onsubmit=sendMessage;$('message').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();$('chat-form').requestSubmit();}};
  $('feedback-open').onclick=()=>snapshot?.authenticated?$('feedback-dialog').showModal():login();$('feedback-close').onclick=()=>$('feedback-dialog').close();$('feedback-form').onsubmit=async e=>{e.preventDefault();try{await api('feedback/',{rating:Number($('rating').value),comment:$('comment').value});$('feedback-dialog').close();$('comment').value='';notify(t('thanks'),false,true);}catch(err){notify(err.message,true);}};
  refresh().then(async s=>{if(s.authenticated){conversation=store.get('p24-portal-conversation')||s.conversations[0]?.id||null;if(conversation)await restore(conversation);await recoverPending();}}).catch(e=>notify(e.message,true));
}
if(typeof module!=='undefined'&&module.exports)module.exports={uuid,markdown,money,inline,safeUrl,normalizeLinks,paymentCard,init,payment,renderState};
if(typeof document!=='undefined')init();
})();
