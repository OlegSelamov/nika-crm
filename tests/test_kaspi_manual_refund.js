"use strict";
// Exercise the real refundSale UI branch without a live bank/KKM.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "static/js/sales.js"), "utf8");
const start = source.indexOf("async function refundSale(id, button = null) {");
const end = source.indexOf("/* Предыдущая реализация", start);
assert(start >= 0 && end > start, "Unable to isolate refundSale function");
const fragment = source.slice(start, end);

async function scenario(sale, confirmations) {
    const requests = [], alerts = [], prompts = [], events = [];
    let bankRefundCalls = 0, refreshed = 0, opened = 0;
    const button = { disabled: false, textContent: "Возврат" };
    const context = {
        console, JSON, String, Boolean, encodeURIComponent,
        CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } },
        window: {
            dispatchEvent(event) { events.push({type: event.type, saleId: event.detail?.saleId}); },
            nikaDesktop: { kaspiPos: { refund() { throw Error("Do not send actual bank requests in tests"); } } }
        },
        document: { body: { contains: () => true } },
        confirm: (prompt) => {
            prompts.push(prompt);
            return confirmations.shift() ?? false;
        },
        alert: text => alerts.push(text),
        loadSalesHistory: () => refreshed++,
        openRefundCheckModal: () => opened++,
        refundKaspiPosLocally: async () => {
            bankRefundCalls++;
            return "refund-test-id";
        },
        fetch: async (url, options = {}) => {
            requests.push({url, options});
            if (!options.method) return {
                ok: true,
                json: async () => sale
            };
            return {
                ok: true,
                json: async () => ({success:true, refund_check_available:true})
            };
        }
    };
    const run = vm.runInNewContext(fragment + "\nrefundSale", context);
    await run(684, button);
    return { requests, prompts, bankRefundCalls, alerts, refreshed, opened, button, events };
}

(async () => {
    const manual = {sale_type:"kaspi", kaspi_transaction_id:null, rekassa_ticket_id:"ticket-684"};
    let s = await scenario(manual, [true, true]);
    assert.equal(s.prompts.length, 2);
    assert(s.prompts[1].includes("ДЕНЬГИ через Kaspi НЕ возвращаются"));
    assert.equal(s.bankRefundCalls, 0);
    assert.equal(s.requests.length, 2);
    assert.deepEqual(JSON.parse(s.requests[1].options.body), {kaspi_manual_fiscal_only:true});
    assert.equal(s.requests[1].url, "/sales/refund/684");
    assert.equal(s.refreshed, 1);
    assert.equal(s.opened, 1);
    assert.deepEqual(s.events, [{type: "nika:sale-refunded", saleId: 684}]);
    assert.equal(s.button.disabled, false);

    s = await scenario(manual, [true, false]);
    assert.equal(s.requests.length, 1, "Canceling the warning must not finalize a fiscal-only return");
    assert.equal(s.bankRefundCalls, 0);
    assert.equal(s.events.length, 0, "Cancellation must not send refund event");
    assert.equal(s.button.disabled, false);

    s = await scenario({...manual,rekassa_ticket_id:null}, [true, true]);
    assert(s.prompts[1].includes("НЕ фискальный чек возврата"));
    assert.equal(s.bankRefundCalls, 0);
    assert.deepEqual(JSON.parse(s.requests[1].options.body), {kaspi_manual_fiscal_only:true});

    const pos = {sale_type:"kaspi", kaspi_transaction_id:"pos-001", kaspi_method:"qr"};
    s = await scenario(pos, [true]);
    assert.equal(s.prompts.length, 1);
    assert.equal(s.bankRefundCalls, 1);
    assert.deepEqual(JSON.parse(s.requests[1].options.body), {
        kaspi_refund_local:true,
        kaspi_refund_transaction_id:"refund-test-id"
    });

    const cash = {sale_type:"cash", kaspi_transaction_id:null};
    s = await scenario(cash, [true]);
    assert.equal(s.prompts.length, 1);
    assert.equal(s.bankRefundCalls, 0);
    assert.deepEqual(JSON.parse(s.requests[1].options.body), {});

    console.log("Kaspi manual-vs-POS refund flow: all 5 cases passed");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
