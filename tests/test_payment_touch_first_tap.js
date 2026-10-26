"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const script = fs.readFileSync(path.join(__dirname, "..", "static/js/sales_payment_touch.js"), "utf8");
const markup = fs.readFileSync(path.join(__dirname, "..", "templates/sales.html"), "utf8");
for (const kind of ["cash", "card", "kaspi"]) {
    assert(markup.includes('data-payment-kind="' + kind + '"'), "Missing tender: " + kind);
}
assert(markup.includes("js/sales_payment_touch.js"), "Payment controller not loaded");
assert(!markup.includes("fillPayment('cash')"), "Inline click must not override editing");

function scenario({electron = true, wide = false} = {}) {
    const windowListeners = {};
    const inputs = {};
    const inputIds = {cash: "cashInput", card: "cardInput", kaspi: "kaspiInput"};
    let focusForced = 0, selected = 0;
    for (const [kind, id] of Object.entries(inputIds)) {
        const listeners = {};
        const classes = new Set();
        inputs[kind] = {
            id, dataset: {paymentKind: kind}, value: "", readOnly: false, inputMode: "decimal",
            listeners, classes,
            classList: {
                toggle(name, enabled) { if (enabled) classes.add(name); else classes.delete(name); },
                remove(name) { classes.delete(name); }
            },
            addEventListener(type, handler) { listeners[type] = handler; },
            select() { selected++; }
        };
    }
    const document = {
        readyState: "complete",
        activeElement: {
            blur() { document.activeElement = null; }
        },
        getElementById(id) { return Object.values(inputs).find(v => v.id === id) || null; }
    };
    const window = {
        nikaDesktop: {isElectron: electron},
        fillPayment(kind) { inputs[kind].value = "1250"; },
        matchMedia() { return {matches: wide}; },
        addEventListener(name, handler) {
            (windowListeners[name] ||= []).push(handler);
        }
    };
    vm.runInNewContext(script, {window, document, console});
    assert(windowListeners.pointerdown?.length, "Capture handler was not installed");

    function tap(kind, pointerType = "touch") {
        const input = inputs[kind];
        let prevented = false;
        const event = {target: input, pointerType, preventDefault() { prevented = true; }};
        windowListeners.pointerdown[0](event);
        // Model native focus guard: it must skip readonly elements.
        if (!prevented && !input.readOnly) {
            focusForced++;
            document.activeElement = input;
            input.listeners.focus?.();
        }
        input.listeners.click?.();
        return prevented;
    }
    function completed() {
        for (const cb of windowListeners["nika:sale-completed"] || []) cb();
    }
    return {inputs, tap, completed, get focusForced() {return focusForced;}, get selected() {return selected;}};
}

// Electron + touch monitor: first tap selects tender WITHOUT focusing.
let app = scenario({electron: true});
assert.equal(app.tap("cash"), true);
assert.equal(app.inputs.cash.value, "1250");
assert.equal(app.inputs.cash.readOnly, true);
assert.equal(app.inputs.cash.inputMode, "none");
assert.equal(app.focusForced, 0);
assert.equal(app.tap("cash"), false);
assert.equal(app.inputs.cash.readOnly, false);
assert.equal(app.focusForced, 1);
assert.equal(app.selected, 1, "Second tap selects full amount for correction");

// Tender change must be one-tap and clear previous payment.
assert.equal(app.tap("card"), true);
assert.equal(app.inputs.card.value, "1250");
assert.equal(app.inputs.cash.value, "");
assert.equal(app.focusForced, 1);
assert.equal(app.tap("card"), false);
app.inputs.card.value = "1500";
assert.equal(app.tap("card"), false);
assert.equal(app.inputs.card.value, "1500", "Repeated tap must not overwrite manually entered amount");

// Mouse and keyboard users retain first-click editing.
app = scenario({electron: true});
assert.equal(app.tap("kaspi", "mouse"), false);
assert.equal(app.focusForced, 1);
assert.equal(app.inputs.kaspi.value, "1250");

// Wide touch browser behaves like touchscreen POS; phone remains single-tap.
app = scenario({electron: false, wide: true});
assert.equal(app.tap("kaspi"), true);
app = scenario({electron: false, wide: false});
assert.equal(app.tap("kaspi"), false);
assert.equal(app.focusForced, 1);

// After sale completion, next sale is not stuck in readonly editing mode.
app = scenario({electron: true});
assert.equal(app.tap("cash"), true);
app.completed();
assert.equal(app.inputs.cash.readOnly, false);
assert.equal(app.inputs.cash.inputMode, "decimal");
assert.equal(app.tap("cash"), true, "Next sale must start with selection again");
console.log("Touchscreen payment: first tap selection, second tap editing, tender switching and mouse/mobile scenarios passed");
