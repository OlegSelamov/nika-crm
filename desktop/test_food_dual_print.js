// Pure Node regression for the one-click dual-print queue and partial retries.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const src = fs.readFileSync(path.join(__dirname, "main.js"), "utf8");
const from = src.indexOf("const acceptedFoodPrints = new Map()");
const to = src.indexOf("\nfunction registerPrinterIpc()", from);
assert.ok(from !== -1 && to > from, "Dual print queue exists");
let calls = [];
let failKitchen = true;
const settings = {receipt_printer:"Printer A", kitchen_printer:"Printer A"};
const mockPrint = async (job) => {
    calls.push(job.kind);
    if (job.kind === "kitchen" && failKitchen) throw new Error("Кухня отключена");
    return {success:true};
};
const context = {settings, printHtml:mockPrint, Map, Promise, Number, String, Error};
vm.runInNewContext(src.slice(from,to) + "\nthis.dispatch = printFoodOrderBatch;", context);
const payload = {
    orderId: 42, fingerprint: "valid-order-state-42",
    guestHtml: "<div>Гостевой чек 42</div>",
    kitchenHtml: "<div>Кухонный заказ 42</div>"
};
(async () => {
    let result = await context.dispatch(payload);
    assert.equal(result.success, false);
    assert.equal(result.guest.success, true);
    assert.equal(result.kitchen.success, false);
    assert.deepEqual(calls, ["receipt","kitchen"]);
    failKitchen = false;
    result = await context.dispatch(payload);
    assert.equal(result.success, true);
    assert.equal(result.guest.alreadySent, true);
    assert.equal(result.kitchen.success, true);
    assert.deepEqual(calls, ["receipt","kitchen","kitchen"],
        "Do not print guest twice after kitchen failure");
    result = await context.dispatch(payload);
    assert.equal(result.guest.alreadySent, true);
    assert.equal(result.kitchen.alreadySent, true);
    assert.equal(calls.length, 3, "No duplicate jobs for the same saved order");
    settings.kitchen_printer = null;
    result = await context.dispatch({...payload, orderId:43});
    assert.equal(result.success, true);
    assert.equal(result.kitchen.skipped, true);
    assert.deepEqual(calls, ["receipt","kitchen","kitchen","receipt"]);
    settings.kitchen_printer = "Printer B";
    result = await context.dispatch({...payload, orderId:43});
    assert.equal(result.guest.alreadySent, true);
    assert.equal(result.kitchen.success, true);
    assert.equal(calls.at(-1), "kitchen");
    console.log("Food dual receipt and partial retry checks passed");
})().catch(error => {console.error(error);process.exitCode = 1;});
