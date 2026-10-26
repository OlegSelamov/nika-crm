"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "static/js/food_sales.js"), "utf8");
const start = source.indexOf("    async function cancelFoodOrder(orderId, button) {");
const end = source.indexOf("    async function loadFoodOrderHistory(", start);
assert(start >= 0 && end > start, "Missing food cancellation handler");
const fragment = source.slice(start, end);

async function scenario({confirmed = true, active = null, status = 200, busy = false, buttonDisabled = false} = {}) {
    const calls = [];
    const notice = {
        hidden: true, textContent: "",
        classList: {
            values: new Set(),
            add(value) { this.values.add(value); },
            remove(value) { this.values.delete(value); }
        }
    };
    const button = {disabled: buttonDisabled, isConnected: true, textContent: "Отменить заказ"};
    let confirmations = 0, cleared = 0, paymentResets = 0, historyRefreshes = 0;
    const ctx = {
        window: {confirm(message) {
            confirmations++;
            assert(message.includes("Заказ останется в истории"));
            assert(message.includes("бумажные чеки не аннулируются"));
            return confirmed;
        }},
        document: {getElementById(id) {
            assert.equal(id, "foodOrderHistoryNotice");
            return notice;
        }},
        console, encodeURIComponent, JSON, Number,
        currentFoodOrderId: active,
        foodOrderBusy: false, foodCheckoutBusy: busy,
        clearFoodCart() { cleared++; },
        applySavedFoodPaymentMethod() { paymentResets++; },
        async loadFoodOrderHistory() { historyRefreshes++; },
        async fetch(url, options) {
            calls.push({url, options});
            return {
                ok: status === 200,
                async json() {
                    return status === 200
                        ? {success: true}
                        : {success: false, message: "Заказ уже оплачен"};
                }
            };
        }
    };
    const run = vm.runInNewContext(fragment + "\ncancelFoodOrder", ctx);
    await run(125, button);
    return {calls, notice, button, confirmations, cleared, paymentResets, historyRefreshes};
}

(async () => {
    let r = await scenario({active: 125});
    assert.equal(r.calls.length, 1);
    assert.equal(r.calls[0].url, "/api/food/orders/125");
    assert.equal(r.calls[0].options.method, "POST");
    assert.equal(r.calls[0].options.headers["Content-Type"], "application/json");
    assert.deepEqual(JSON.parse(r.calls[0].options.body), {action: "cancel"});
    assert.equal(r.cleared, 1);
    assert.equal(r.paymentResets, 1);
    assert.equal(r.historyRefreshes, 1);
    assert.match(r.notice.textContent, /Заказ №125 отменён/);
    assert.equal(r.button.disabled, false);

    r = await scenario({active: 88});
    assert.equal(r.cleared, 0, "Unrelated checkout cart must be preserved");
    assert.equal(r.historyRefreshes, 1);

    r = await scenario({confirmed: false, active: 125});
    assert.equal(r.calls.length, 0);
    assert.equal(r.cleared, 0);

    r = await scenario({status: 409, active: 125});
    assert.equal(r.cleared, 0, "Rejected cancellation must keep the current cart");
    assert.equal(r.historyRefreshes, 0);
    assert.equal(r.notice.hidden, false);
    assert.match(r.notice.textContent, /Заказ уже оплачен/);
    assert.equal(r.button.disabled, false);

    r = await scenario({busy: true});
    assert.equal(r.confirmations, 0);
    assert.equal(r.calls.length, 0);

    r = await scenario({buttonDisabled: true});
    assert.equal(r.confirmations, 0);
    assert.equal(r.calls.length, 0);

    console.log("Food order cancellation: 6 behavioral scenarios passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
