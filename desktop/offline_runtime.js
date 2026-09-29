const http=require("http"),https=require("https"),path=require("path"),{URL}=require("url");
const {DesktopOfflineStore}=require("./offline_store");
const JSON_HEADERS={"content-type":"application/json; charset=utf-8"};
const NET_ERRORS=new Set([-21,-101,-102,-105,-106,-109,-118]);

function jsonResponse(body,status=200){return {handled:true,status,headers:JSON_HEADERS,bodyText:JSON.stringify(body)}}
function parseJson(text){try{return text?JSON.parse(text):null}catch(_){return null}}
function num(v){const n=Number(String(v??0).replace(",","."));return Number.isFinite(n)?n:0}
function candidates(raw){
  const s=String(raw||"").trim(),out=new Set();
  if(!s)return [];
  out.add(s); const noSym=s.replace(/^\]d2/i,""); out.add(noSym);
  const compact=noSym.replace(/\x1d/g,""); out.add(compact);
  const m=compact.match(/^01(\d{14})/); if(m)out.add(m[1]);
  return Array.from(out).filter(Boolean);
}

function createDesktopOfflineRuntime({app,ipcMain,getWindow,appUrl,legacyMode=false}){
  const store=new DesktopOfflineStore(path.join(app.getPath("userData"),"nika-offline-store.json"));
  const origin=new URL(appUrl).origin;
  let syncState="idle",syncPromise=null,interval=null,switching=false;

  function ses(){const w=getWindow();return w&&!w.isDestroyed()?w.webContents.session:null}
  async function cookieHeader(){
    const s=ses(); if(!s)return "";
    try{return (await s.cookies.get({url:appUrl})).map(c=>c.name+"="+c.value).join("; ")}catch(_){return ""}
  }
  async function requestServer(requestPath,{method="GET",body=null,timeoutMs=10000}={}){
    const u=new URL(requestPath,appUrl); if(u.origin!==origin)throw new Error("External request");
    const cookie=await cookieHeader(), payload=body==null?null:(typeof body==="string"?body:JSON.stringify(body));
    const transport=u.protocol==="http:"?http:https;
    return new Promise((resolve,reject)=>{
      const req=transport.request({
        protocol:u.protocol,hostname:u.hostname,port:u.port||undefined,
        path:u.pathname+u.search,method,
        headers:{
          Accept:"application/json, text/plain, */*",
          "Accept-Encoding":"identity",
          ...(payload!=null?{"Content-Type":"application/json; charset=utf-8"}:{}),
          ...(cookie?{Cookie:cookie}:{})
        }
      },res=>{
        const chunks=[]; res.on("data",c=>chunks.push(Buffer.from(c)));
        res.on("end",()=>{
          const bodyText=Buffer.concat(chunks).toString("utf8");
          resolve({status:res.statusCode||0,headers:{"content-type":res.headers["content-type"]||JSON_HEADERS["content-type"]},bodyText,json:parseJson(bodyText)});
        });
      });
      req.on("error",reject); req.setTimeout(timeoutMs,()=>req.destroy(new Error("timeout")));
      if(payload!=null)req.write(payload); req.end();
    });
  }

  function cache(){return store.state().cache||{}}
  function filterRows(rows,q){
    const n=String(q||"").trim().toLowerCase(); if(!n)return Array.isArray(rows)?rows:[];
    return (Array.isArray(rows)?rows:[]).filter(r=>[
      r&&r.name,r&&r.barcode,r&&r.gtin,r&&r.ntin,r&&r.category,
      r&&r.full_name,r&&r.company_name,r&&r.phone,r&&r.iin
    ].some(v=>String(v||"").toLowerCase().includes(n)));
  }
  function findItem(code){
    const c=cache(),rows=[...(Array.isArray(c.stock)?c.stock:[]),...(Array.isArray(c.items)?c.items:[])];
    for(const x of candidates(code)){const item=rows.find(r=>[r.barcode,r.gtin,r.ntin].some(v=>String(v||"")===x)); if(item)return item}
    return null;
  }
  function barcodePayload(item,raw){
    if(!item)return {found:false,offline:true};
    const gtin=String(item.gtin||"")||candidates(raw).find(x=>/^\d{14}$/.test(x))||"";
    return {found:true,offline:true,id:item.id,name:item.name||"",price:num(item.retail_price??item.price),retail_price:num(item.retail_price??item.price),purchase_price:num(item.purchase_price),unit:item.unit||"шт",category:item.category||"",barcode:item.barcode||"",gtin,ntin:item.ntin||"",item_type:item.item_type||"product",quantity:num(item.stock??item.quantity),stock:num(item.stock??item.quantity),excise_stamp:String(raw||"").length>14?String(raw):""};
  }

  function fallback(url,method,body){
    const c=cache(),p=url.pathname,q=url.searchParams.get("q")||"";
    if(method==="POST"&&p==="/api/barcode")return jsonResponse(barcodePayload(findItem(body&&body.barcode),body&&body.barcode));
    if(method!=="GET")return null;
    if(p.startsWith("/api/barcode-info/")){
      const code=decodeURIComponent(p.slice("/api/barcode-info/".length)),item=findItem(code);
      return jsonResponse(item?barcodePayload(item,code):{found:false,offline:true,name:"",gtin:"",ntin:""});
    }
    if(p==="/api/items/search"){const rows=filterRows(c.items,q);return jsonResponse({items:rows.slice(0,30),has_more:rows.length>30,offline:true})}
    if(p==="/api/items")return jsonResponse(filterRows(c.items,q));
    if(p==="/api/stock"){
      let rows=filterRows(c.stock,q);
      const scope=url.searchParams.get("stock_scope")||"all";
      const category=(url.searchParams.get("category")||"").trim().toLowerCase();
      const status=(url.searchParams.get("status")||"all").trim().toLowerCase();
      const sort=(url.searchParams.get("sort")||"name").trim().toLowerCase();

      if(scope==="income"){
        rows=rows.filter(r=>["product","ingredient"].includes(String(r.item_type||"product")));
      }
      if(category){
        rows=rows.filter(r=>String(r.category||"").toLowerCase()===category);
      }
      if(status==="normal") rows=rows.filter(r=>num(r.stock)>5);
      else if(status==="low") rows=rows.filter(r=>num(r.stock)>0&&num(r.stock)<=5);
      else if(status==="out") rows=rows.filter(r=>num(r.stock)<=0);

      rows=[...rows].sort((a,b)=>{
        if(sort==="stock-asc") return num(a.stock)-num(b.stock);
        if(sort==="stock-desc") return num(b.stock)-num(a.stock);
        if(sort==="retail-asc") return num(a.retail_price)-num(b.retail_price);
        if(sort==="retail-desc") return num(b.retail_price)-num(a.retail_price);
        return String(a.name||"").localeCompare(String(b.name||""),"ru");
      });

      if(!url.search) return jsonResponse(rows);

      const limit=Math.max(1,Math.min(Number(url.searchParams.get("limit")||50),100));
      const offset=Math.max(0,Number(url.searchParams.get("offset")||0));
      const items=rows.slice(offset,offset+limit);
      return jsonResponse({
        items,
        total:rows.length,
        offset,
        limit,
        has_more:offset+items.length<rows.length,
        offline:true
      });
    }
    if(p==="/api/stock/movements")return jsonResponse(Array.isArray(c.movements)?c.movements:[]);
    if(p==="/api/company/active")return jsonResponse(c.company_active||{});
    if(p==="/api/clients")return jsonResponse(filterRows(c.clients,q));
    if(p==="/api/categories")return jsonResponse(Array.isArray(c.categories)?c.categories:[]);
    if(p==="/api/suppliers")return jsonResponse(Array.isArray(c.suppliers)?c.suppliers:[]);
    return null;
  }

  function cacheResponse(url,json){
    const p=url.pathname;
    if(p==="/api/items"&&Array.isArray(json))store.cache("items",json);
    else if(p==="/api/stock"&&Array.isArray(json))store.cache("stock",json);
    else if(p==="/api/clients"&&Array.isArray(json))store.cache("clients",json);
    else if(p==="/api/categories"&&Array.isArray(json))store.cache("categories",json);
    else if(p==="/api/stock/movements"&&Array.isArray(json))store.cache("movements",json);
    else if(p==="/api/suppliers"&&Array.isArray(json))store.cache("suppliers",json);
    else if(p==="/api/company/active"&&json&&typeof json==="object")store.cache("company_active",json);
  }
  function opType(p){return p==="/sales/pay"?"sale":p==="/api/stock/income"?"stock_income":p==="/api/stock/writeoff"?"stock_writeoff":p==="/api/mobile/stock/income/supplier"?"stock_income_supplier":null}
  function queued(op){
    const base={success:true,queued:true,pending:true,operation_id:op.operation_id};
    return op.operation_type==="sale"?{...base,sale_id:null,fiscalized:false,rekassa_required:true,rekassa:{status:"PENDING",message:"Ожидает синхронизации и фискализации"}}:{...base,movement_id:null,pricing:{}};
  }
  function retryable(s){return s===0||s===401||s===408||s===425||s===429||s>=500}
  async function sendOp(op){
    return requestServer(op.path,{method:op.method||"POST",body:{...(op.body||{}),operation_id:op.operation_id},timeoutMs:op.operation_type==="sale"?70000:20000});
  }
  async function submitOperation(type,p,body){
    const op=store.createOperation(type,p,body); store.markSyncing(op.operation_id);
    try{
      const r=await sendOp(op),j=r.json;
      if(r.status>=200&&r.status<300){
        if(j&&j.pending===true){store.applyOptimistic(op.operation_id);store.markPending(op.operation_id);return jsonResponse({...queued(op),...j,queued:true})}
        store.markSynced(op.operation_id); return {handled:true,status:r.status,headers:r.headers,bodyText:r.bodyText};
      }
      if(retryable(r.status)){store.applyOptimistic(op.operation_id);store.markPending(op.operation_id,(j&&(j.error||j.message))||("HTTP "+r.status));return jsonResponse(queued(op))}
      store.markError(op.operation_id,(j&&(j.error||j.message))||("HTTP "+r.status)); return {handled:true,status:r.status,headers:r.headers,bodyText:r.bodyText};
    }catch(e){store.applyOptimistic(op.operation_id);store.markPending(op.operation_id,e.message);return jsonResponse(queued(op))}
  }
  async function flushQueue(){
    for(const op of store.pendingOperations(50)){
      store.markSyncing(op.operation_id);
      try{
        const r=await sendOp(op),j=r.json;
        if(r.status>=200&&r.status<300){if(j&&j.pending===true){store.markPending(op.operation_id);break} store.markSynced(op.operation_id);continue}
        if(retryable(r.status)){store.markPending(op.operation_id,(j&&(j.error||j.message))||("HTTP "+r.status));break}
        store.markError(op.operation_id,(j&&(j.error||j.message))||("HTTP "+r.status));
      }catch(e){store.markPending(op.operation_id,e.message);break}
    }
  }
  async function fetchCache(p,name){
    try{const r=await requestServer(p,{timeoutMs:12000});if(r.status>=200&&r.status<300){if(r.json!=null)store.cache(name,r.json);return true}}catch(_){}
    return false;
  }
  async function syncNow(force=false){
    if(syncPromise)return syncPromise;
    syncPromise=(async()=>{
      syncState="syncing";
      try{
        const p=await requestServer("/api/mobile/profile",{timeoutMs:force?10000:6000});
        if(p.status<200||p.status>=300||!p.json)throw new Error("offline");
        store.setActiveIdentity(p.json);
        await flushQueue();
        await Promise.all([
          fetchCache("/api/items","items"),fetchCache("/api/stock","stock"),
          fetchCache("/api/clients","clients"),fetchCache("/api/categories","categories"),
          fetchCache("/api/stock/movements","movements"),fetchCache("/api/suppliers","suppliers"),
          fetchCache("/api/company/active","company_active")
        ]);
        store.cache("profile",p.json);store.markSyncedNow();syncState="synced";
      }catch(_){syncState="offline"}finally{syncPromise=null}
      return state();
    })();
    return syncPromise;
  }
  function state(){return {...store.state(),sync_state:syncState,legacy:legacyMode}}
  function supportedGet(p){return ["/api/items","/api/items/search","/api/stock","/api/stock/movements","/api/clients","/api/categories","/api/suppliers","/api/company/active"].includes(p)||p.startsWith("/api/barcode-info/")}
  async function intercepted(payload={}){
    const u=new URL(payload.url||"/",appUrl); if(u.origin!==origin)return {handled:false};
    const method=String(payload.method||"GET").toUpperCase(),body=parseJson(payload.bodyText||"")||{},type=opType(u.pathname);
    if(method==="POST"&&type)return submitOperation(type,u.pathname,body);
    const barcode=method==="POST"&&u.pathname==="/api/barcode";
    if(!barcode&&!(method==="GET"&&supportedGet(u.pathname)))return {handled:false};
    try{
      const r=await requestServer(u.pathname+u.search,{method,body:method==="GET"?null:body,timeoutMs:8000});
      if(r.status>=200&&r.status<300){cacheResponse(u,r.json);return {handled:true,status:r.status,headers:r.headers,bodyText:r.bodyText}}
      const fb=fallback(u,method,body); if(fb&&retryable(r.status))return fb;
      return {handled:true,status:r.status,headers:r.headers,bodyText:r.bodyText};
    }catch(_){return fallback(u,method,body)||{handled:false}}
  }
  async function switchOffline(w){
    if(switching||!w||w.isDestroyed()||w.webContents.getURL().startsWith("file:"))return;
    switching=true;try{await w.loadFile(path.join(__dirname,"offline.html"))}catch(e){console.error(e)}finally{switching=false}
  }
  function attachWindow(w){
    w.webContents.on("did-fail-load",(ev,code,desc,url,isMainFrame)=>{
      if(isMainFrame===false||!NET_ERRORS.has(code))return;
      try{if(new URL(url||appUrl,appUrl).origin===origin)switchOffline(w)}catch(_){}
    });
    w.webContents.on("did-finish-load",()=>{if(w.webContents.getURL().startsWith(origin))setTimeout(()=>syncNow(false).catch(()=>{}),800)});
    w.webContents.on("will-navigate",(ev,target)=>{try{const u=new URL(target);if(u.origin===origin&&u.pathname==="/logout")store.clearActiveIdentity()}catch(_){}});
  }

  ipcMain.handle("offline:get-state",async()=>state());
  ipcMain.handle("offline:sync",async()=>syncNow(true));
  ipcMain.handle("offline:request",async(event,payload)=>intercepted(payload||{}));
  ipcMain.handle("offline:submit",async(event,payload={})=>{
    const p=String(payload.path||""),type=opType(p);if(!type)throw new Error("Unsupported offline operation");
    const r=await submitOperation(type,p,payload.body||{});setTimeout(()=>syncNow(false).catch(()=>{}),200);
    return {...(parseJson(r.bodyText)||{}),http_status:r.status};
  });
  ipcMain.handle("offline:open-online",async()=>{const w=getWindow();if(!w||w.isDestroyed())return false;await w.loadURL(appUrl);return true});

  interval=setInterval(()=>syncNow(false).catch(()=>{}),5*60*1000);
  return {attachWindow,syncNow,state,dispose(){if(interval)clearInterval(interval);interval=null}};
}
module.exports={createDesktopOfflineRuntime};