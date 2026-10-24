/* Browser-like behavioral regressions for the retail-only manual cart flow.
   Run with: node tests/test_retail_manual_cart.js */
"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const script = fs.readFileSync(path.join(__dirname, "../static/js/retail_cart_drafts.js"), "utf8");

const makeNode = () => ({
    textContent: "", value: "", disabled: false, style: {}, children: [],
    classList: {toggle() {}, contains() {return false;}},
    handlers: {},
    addEventListener(type, fn) {this.handlers[type] = fn;},
    click() {if (this.handlers.click) return this.handlers.click();},
    replaceChildren() {this.children = [];},
    append(...children) {this.children.push(...children);},
    appendChild(node) {this.children.push(node);},
});

function setup({initialCart = [], initialSaved = [], saveError = false, saveDeferred = null} = {}) {
    const nodes = new Map();
    const getNode = id => {
        if (!nodes.has(id)) nodes.set(id, makeNode());
        return nodes.get(id);
    };
    const saved = new Map(initialSaved.map(x => [x.id, structuredClone(x)]));
    const calls = [];
    let nextId = 100;
    const json = (obj, status = 200) => ({
        ok: status >= 200 && status < 300, status, json: async () => obj
    });
    let resets = 0, renders = 0;
    const scope = {
        cart: structuredClone(initialCart),
        selectedClient: 77,
        selectedClientData: {id:77, full_name:"Выбранный клиент"},
        salePaymentBusy: false,
        invoiceCreationBusy: false,
        NIKA_RETAIL_DRAFT_OWNER: [4, 55],
        NIKA_BUSINESS_MODE: "retail",
        document: {
            body: {classList: {contains() {return false;}}},
            getElementById: getNode,
            createElement: makeNode,
        },
        timers: [],
        setTimeout(fn) {return 1;}, clearTimeout() {},
        confirm() {return true;}, alert(msg) {throw new Error("Unexpected alert: " + msg);},
        events: {},
        addEventListener(name, fn) {this.events[name] = fn;},
        dispatchEvent(evt) {if (this.events[evt.type]) this.events[evt.type](evt);},
        renderCart() {renders++;},
        resetSaleAmounts() {resets++;},
        selectDefaultPrivateClient() {
            scope.selectedClient = 1;
            scope.selectedClientData = {id:1, full_name:"Частное лицо"};
            getNode("clientSearch").value = "Частное лицо";
        },
        switchSalesTab(tab) {scope.lastTab = tab;},
        fetch: async (url, options = {}) => {
            const method = options.method || "GET";
            calls.push({url, method, payload: options.body ? JSON.parse(options.body) : null});
            if (url === "/api/sales/cart-drafts" && method === "POST") {
                if (saveDeferred) await saveDeferred.promise;
                if (saveError) return json({success:false,error:"Нет связи"}, 503);
                const data = JSON.parse(options.body);
                assert.equal(data.is_auto, false);
                const id = data.id || nextId++;
                saved.set(id, {...data, id, is_auto:false, updated_at:"2026-10-24T14:00:00", items_count:data.cart.length});
                return json({success:true,id});
            }
            if (url === "/api/sales/cart-drafts" && method === "GET") {
                return json({success:true,drafts:[...saved.values()]});
            }
            const match = /^\/api\/sales\/cart-drafts\/(\d+)$/.exec(url);
            if (match) {
                const id = Number(match[1]);
                if (method === "DELETE") {saved.delete(id); return json({success:true,deleted:true});}
                if (saved.has(id)) return json({success:true,draft:saved.get(id)});
                return json({success:false,error:"Not found"}, 404);
            }
            if (url.endsWith("/repeat-cart")) return json({
                success:true, cart:[{id:90,name:"Повтор",qty:1,price:99}],
                client_id:77, client_name:"Покупатель"
            });
            throw new Error("Unexpected request " + method + " " + url);
        }
    };
    scope.window = scope;
    scope.localStorage = {getItem() {throw new Error("Forbidden automatic local restore");},
                          setItem() {throw new Error("Forbidden automatic local save");}};
    const context = vm.createContext(scope);
    vm.runInContext(script, context);
    getNode("clientSearch").value = "Выбранный клиент";
    scope.events.load();
    return {scope, getNode, saved, calls, get renders(){return renders;}, get resets(){return resets;}};
}
const item = id => ({id, name:"Товар " + id, qty:1, price:100, unit:"шт"});
const flush = async () => {for (let i = 0; i < 8; i++) await new Promise(r => setImmediate(r));};

async function testNoAutosaveOrRestore() {
    const app = setup({initialCart:[item(2)], initialSaved:[{
        id:11, title:"Старая корзина", cart:[item(3)], client_id:77, client_name:"Клиент",
        updated_at:"2026-10-24T13:00:00", items_count:1, is_auto:true
    }]});
    assert.equal(app.scope.cart[0].id, 2, "Startup must not replace current sale");
    assert.equal(app.calls.length, 0, "No background requests even to list drafts");
    app.scope.cart.push(item(5));
    app.scope.renderCart();
    await flush();
    assert.equal(app.calls.length, 0, "No writes after rendering or editing cart");
    app.getNode("historyTabBtn").click();
    await flush();
    assert.equal(app.calls.filter(x => x.method === "GET").length, 1);
    assert.match(app.getNode("retailDraftList").children[0].children[0].children[0].textContent,
        /Старая автокорзина/);
    assert.equal(app.calls.filter(x => x.method === "POST").length, 0);
}

async function testManualSaveParksCartAndNewSale() {
    const app = setup({initialCart:[item(2)]});
    app.getNode("retailSaveCart").click();
    await flush();
    const posts = app.calls.filter(x => x.method === "POST");
    assert.equal(posts.length, 1);
    assert.equal(posts[0].payload.cart[0].id, 2);
    assert.equal(app.saved.size, 1);
    assert.equal(app.scope.cart.length, 0, "Successful parking frees register");
    assert.equal(app.scope.selectedClient, 1, "Next sale gets default private client");
    assert.ok(app.resets > 0);
    app.scope.cart.push(item(9));
    app.scope.renderCart();
    await flush();
    assert.equal(app.calls.filter(x => x.method === "POST").length, 1,
        "New sale cannot overwrite saved draft in background");
}

async function testResumeAndPaymentConsumes() {
    const app = setup({initialSaved:[{
        id:77,title:"Ранее сохранено",cart:[item(12)],
        client_id:88,client_name:"ИП Покупатель",updated_at:"2026-10-24T14:00:00",
        items_count:1,is_auto:false
    }]});
    app.scope.cart = [];
    app.getNode("historyTabBtn").click();
    await flush();
    const button = app.getNode("retailDraftList").children[0].children[1].children[0];
    button.click();
    await flush();
    assert.equal(app.scope.cart[0].id, 12);
    assert.equal(app.scope.selectedClient, 88);
    assert.equal(app.scope.lastTab, "cart");
    app.scope.salePaymentBusy = true;
    app.scope.cart = [];
    app.scope.renderCart();
    app.scope.dispatchEvent({type:"nika:sale-completed"});
    await flush();
    assert.equal(app.saved.has(77), false, "Paid draft must disappear from parked carts");
    assert.equal(app.calls.filter(x => x.method === "POST").length, 0,
        "Resuming and paying must never generate auto-save");
}

async function testFailedSaveKeepsCart() {
    const app = setup({initialCart:[item(2)],saveError:true});
    app.getNode("retailSaveCart").click();
    await flush();
    assert.equal(app.scope.cart.length, 1, "Save failure keeps working sale intact");
    assert.equal(app.scope.selectedClient, 77);
    assert.equal(app.saved.size, 0);
}

async function testChangesDuringSlowSaveAreNotLost() {
    let resolve;
    const deferred = {promise:new Promise(r => {resolve=r;})};
    const app = setup({initialCart:[item(2)],saveDeferred:deferred});
    app.getNode("retailSaveCart").click();
    await flush();
    app.scope.cart.push(item(9));
    app.scope.renderCart();
    resolve();
    await flush();
    assert.equal(app.saved.size, 1);
    assert.equal([...app.saved.values()][0].cart.length, 1);
    assert.equal(app.scope.cart.length, 2, "Never wipe edits made while POST is pending");
}

async function testClearingResumedCartDoesNotOverwriteOld() {
    const app = setup({initialSaved:[{
        id:71,title:"Заказ А",cart:[item(2)],
        client_id:77,client_name:"Клиент",updated_at:"2026-10-24T13:00:00",
        items_count:1,is_auto:false
    }]});
    app.scope.cart = [];
    app.getNode("historyTabBtn").click();
    await flush();
    app.getNode("retailDraftList").children[0].children[1].children[0].click();
    await flush();
    app.scope.cart = [];
    app.scope.renderCart(); // Operator removes all goods manually.
    app.scope.cart.push(item(8));
    app.getNode("retailSaveCart").click();
    await flush();
    assert.equal(app.saved.size, 2, "Old parked basket must not be overwritten");
    assert.equal(app.saved.get(71).cart[0].id, 2);
}

async function testFoodModeCannotParkRetailCart() {
    const app = setup({initialCart:[item(2)]});
    app.scope.NIKA_BUSINESS_MODE = "foodservice";
    app.getNode("retailSaveCart").click();
    await flush();
    assert.equal(app.calls.length, 0);
    assert.equal(app.scope.cart.length, 1);
}

(async () => {
    await testNoAutosaveOrRestore();
    await testManualSaveParksCartAndNewSale();
    await testResumeAndPaymentConsumes();
    await testFailedSaveKeepsCart();
    await testChangesDuringSlowSaveAreNotLost();
    await testClearingResumedCartDoesNotOverwriteOld();
    await testFoodModeCannotParkRetailCart();
    console.log("7 retail manual-cart behavioral checks passed");
})().catch(error => {console.error(error);process.exitCode = 1;});