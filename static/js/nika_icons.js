(()=>{
if(window.__NIKA_ICONS_READY__)return;window.__NIKA_ICONS_READY__=true;
const S={
menu:'<path d="M4 7h16M4 12h16M4 17h16"/>',
users:'<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
send:'<path d="m22 2-7 20-4-9-9-4 20-7Z"/><path d="M22 2 11 13"/>',
refresh:'<path d="M20 7h-5V2M4 17h5v5M5 9a8 8 0 0 1 13-4l2 2M19 15a8 8 0 0 1-13 4l-2-2"/>',
mic:'<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0M12 17v5M8 22h8"/>',
school:'<path d="M3 21h18M5 21V9l7-5 7 5v12M9 21v-6h6v6M8 11h.01M16 11h.01M12 4V1l4 2-4 1"/>',
check:'<path d="m5 12 4 4L19 6"/>',
close:'<path d="M6 6l12 12M18 6 6 18"/>',
file:'<path d="M6 2h8l4 4v16H6zM14 2v5h5M9 13h6M9 17h6"/>',
calendar:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/>',
folder:'<path d="M3 6h7l2 2h9v11H3z"/>',
trash:'<path d="M3 6h18M8 6V4h8v2M19 6l-1 15H6L5 6M10 10v7M14 10v7"/>',
restore:'<path d="M9 7H4v5"/><path d="M5 11a8 8 0 1 0 2-5"/>',
building:'<path d="M4 21V5h10v16M14 9h6v12M7 8h2M7 12h2M7 16h2M17 12h1M17 16h1M2 21h20"/>',
printer:'<path d="M6 9V3h12v6M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2M6 14h12v8H6z"/>',
globe:'<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18"/>',
wrench:'<path d="M14 6a4 4 0 0 0 4 4l3-3a6 6 0 0 1-8 8L6 22l-4-4 7-7a6 6 0 0 1 8-8z"/>',
car:'<path d="M5 17h14l-1-6-2-4H8l-2 4-1 6Z"/><path d="M3 13h18M7 17v2M17 17v2"/>',
truck:'<path d="M3 6h11v11H3zM14 10h4l3 4v3h-7z"/><circle cx="7" cy="19" r="2"/><circle cx="18" cy="19" r="2"/>',
package:'<path d="m21 8-9 5-9-5 9-5 9 5Z"/><path d="m3 8 9 5 9-5v9l-9 5-9-5Z"/>',
bank:'<path d="m3 10 9-6 9 6M5 10v8M9 10v8M15 10v8M19 10v8M3 18h18M2 21h20"/>',
card:'<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 9h20M6 15h4"/>',
megaphone:'<path d="M3 11v2h4l9 4V7l-9 4zM7 13l2 6h3"/>',
tools:'<path d="M14 6a4 4 0 0 0 4 4l3-3a6 6 0 0 1-8 8L6 22l-4-4 7-7a6 6 0 0 1 8-8z"/><path d="m14 14 7 7"/>',
receipt:'<path d="M6 2h12v20l-3-2-3 2-3-2-3 2zM9 7h6M9 11h6M9 15h4"/>',
external:'<path d="M14 3h7v7M21 3l-9 9"/><path d="M18 13v7H4V6h7"/>',
edit:'<path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4Z"/>',
lock:'<rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
chart:'<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
money:'<rect x="2" y="5" width="20" height="14" rx="2"/><circle cx="12" cy="12" r="3"/><path d="M6 9H5v2M18 15h1v-2"/>',
monitor:'<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8M12 17v4"/>',
phone:'<rect x="7" y="2" width="10" height="20" rx="2"/><path d="M11 18h2"/>',
scale:'<path d="M12 3v18M5 7h14M5 7l-3 6h6L5 7ZM19 7l-3 6h6l-3-6ZM8 21h8"/>',
camera:'<path d="M4 7h4l2-3h4l2 3h4v13H4z"/><circle cx="12" cy="13" r="4"/>',
volume:'<path d="M4 10h4l5-4v12l-5-4H4zM17 9a4 4 0 0 1 0 6M19 6a8 8 0 0 1 0 12"/>',
vibrate:'<rect x="8" y="4" width="8" height="16" rx="2"/><path d="M4 8v8M20 8v8M2 10v4M22 10v4"/>',
move:'<path d="M12 3v18M8 7l4-4 4 4M8 17l4 4 4-4"/>',
heart:'<path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8z"/>',
cart:'<path d="M3 3h2l2 13h10l3-9H6M9 21h.01M17 21h.01"/>',
warning:'<path d="M12 3 2 21h20L12 3Z"/><path d="M12 9v5M12 18h.01"/>',
bag:'<path d="M5 8h14l1 13H4L5 8Z"/><path d="M9 8V6a3 3 0 0 1 6 0v2"/>',
arrowLeft:'<path d="M19 12H5M11 6l-6 6 6 6"/>',
arrowRight:'<path d="M5 12h14M13 6l6 6-6 6"/>',
bell:'<path d="M18 8a6 6 0 1 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>',
spark:'<path d="m12 3 1.4 4.2L18 9l-4.6 1.8L12 15l-1.4-4.2L6 9l4.6-1.8L12 3ZM19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15Z"/>',
search:'<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
database:'<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
barcode:'<path d="M3 5v14M6 5v14M10 5v14M13 5v14M18 5v14M21 5v14"/>',
download:'<path d="M12 3v12m-5-5 5 5 5-5M5 21h14"/>',
upload:'<path d="M12 21V9m-5 5 5-5 5 5M5 3h14"/>',
clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
list:'<path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01"/>',
hash:'<path d="M10 3 8 21M16 3l-2 18M4 9h16M3 15h16"/>',
rotateLeft:'<path d="M9 7H4v5"/><path d="M5 11a8 8 0 1 0 2-5"/>',
sale:'<path d="M4 7h16v12H4zM7 4h10v3M8 12h8M8 15h5"/>',
tag:'<path d="M20 13 13 20 4 11V4h7z"/><circle cx="8.5" cy="8.5" r="1.5"/>',
image:'<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8.5" cy="9" r="1.5"/><path d="m21 15-5-5L5 20"/>',
plus:'<path d="M12 5v14M5 12h14"/>',
play:'<path d="m8 5 11 7-11 7z"/>'
};
function inject(){if(document.getElementById('nikaGlobalIconSprite'))return;const s=document.createElementNS('http://www.w3.org/2000/svg','svg');s.id='nikaGlobalIconSprite';s.classList.add('nika-icon-sprite');s.setAttribute('aria-hidden','true');s.innerHTML='<defs>'+Object.entries(S).map(([k,v])=>'<symbol id="nika-'+k+'" viewBox="0 0 24 24">'+v+'</symbol>').join('')+'</defs>';document.body.prepend(s);}
const M=new Map([['📄','file'],['📅','calendar'],['📁','folder'],['✓','check'],['✔','check'],['✅','check'],['👥','users'],['🗑','trash'],['↩','restore'],['🏢','building'],['🖨','printer'],['🔄','refresh'],['❌','close'],['✕','close'],['🌐','globe'],['🔧','wrench'],['🚗','car'],['🔝','external'],['🔥','spark'],['💰','money'],['📦','package'],['🏦','bank'],['🚚','truck'],['⚡','spark'],['🏛','bank'],['💳','card'],['📣','megaphone'],['🛠','tools'],['🧾','receipt'],['↗','external'],['✎','edit'],['🔒','lock'],['📊','chart'],['🖥','monitor'],['📱','phone'],['⚖','scale'],['📷','camera'],['🔊','volume'],['📳','vibrate'],['↕','move'],['♡','heart'],['♥','heart'],['🛒','cart'],['⚠','warning'],['🛍','bag'],['👈','arrowLeft'],['👉','arrowRight'],['🏫','school'],['🎙','mic'],['➤','send'],['🔔','bell'],['✦','spark'],['▶','play']]);
const K=[...M.keys()].sort((a,b)=>b.length-a.length);
const esc=t=>t.replace(/[.*+?^$()|[\]\\{}]/g,'\\$&');
const R=new RegExp(K.map(esc).join('|'),'gu');
function I(n){const x=document.createElement('span');x.className='nika-emoji-icon';x.setAttribute('aria-hidden','true');x.innerHTML='<svg class="nika-ui-icon"><use href="#nika-'+n+'"></use></svg>';return x;}
function text(n){const v=n.nodeValue||'';R.lastIndex=0;if(!R.test(v)){R.lastIndex=0;return;}R.lastIndex=0;const f=document.createDocumentFragment();let p=0;v.replace(R,(m,o)=>{f.append(v.slice(p,o));f.append(I(M.get(m)));p=o+m.length;return m;});f.append(v.slice(p));n.replaceWith(f);}
function norm(root){const w=document.createTreeWalker(root||document.body,NodeFilter.SHOW_TEXT),a=[];while(w.nextNode())a.push(w.currentNode);for(const n of a){const p=n.parentElement;if(!p||['SCRIPT','STYLE','TEXTAREA','INPUT','OPTION','TITLE'].includes(p.tagName))continue;text(n);}}
function boot(){inject();norm(document.body);new MutationObserver(ms=>ms.forEach(m=>m.addedNodes.forEach(n=>{if(n.nodeType===3)text(n);else if(n.nodeType===1)norm(n)}))).observe(document.documentElement,{childList:true,subtree:true});}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
})();