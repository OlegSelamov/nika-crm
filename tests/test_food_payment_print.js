// Run the real payExistingFoodOrder() handler with mocked payment and print
// providers. Confirms cash, card and Kaspi print BEFORE the sale starts.
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const path = require("node:path");
const src = fs.readFileSync(path.join(__dirname, "../static/js/food_sales.js"), "utf8");
const start = src.indexOf("    async function payExistingFoodOrder() {");
const end = src.indexOf("\n    function newFoodOrder()", start);
assert.ok(start >= 0 && end > start, "Could not locate checkout function");
const functionCode = src.slice(start, end);

async function checkout(method, {alreadyPrinted=false, failPrint=false}={}) {
    const calls = [];
    const button = {disabled:false};
    const sandbox = {
        getCart:()=>[{id:1, qty:1}],
        window:{nikaKaspiPosActive:false},
        foodCheckoutBusy:false,
        document:{getElementById:()=>button},
        foodMessage:(message)=>calls.push("message:"+message),
        showFoodPrintStatus:()=>{},
        isFoodTicketCurrent:()=>alreadyPrinted,
        saveFoodOrder:async()=>{calls.push("save");return {id:42};},
        printBothFoodTickets:async()=>{calls.push("print");return !failPrint;},
        openCashChangeModal:()=>calls.push("cash"),
        pay:()=>calls.push("pay"),
        currentSavedPlannedMethod:method,
        console
    };
    vm.runInNewContext(functionCode+"\nthis.handler=payExistingFoodOrder;",sandbox);
    await sandbox.handler();
    assert.equal(button.disabled,false,"Checkout button must unlock");
    return calls;
}
(async()=>{
    for(const method of ["cash","card","kaspi"]) {
        const result = await checkout(method);
        assert.deepEqual(result,["save","print",method==="cash"?"cash":"pay"],
            "First confirmation should save and print then pay for "+method);
        assert.deepEqual(await checkout(method,{alreadyPrinted:true}),
            [method==="cash"?"cash":"pay"],"Never reprint an unchanged order");
        const failed = await checkout(method,{failPrint:true});
        assert.deepEqual(failed.slice(0,2),["save","print"]);
        assert.ok(!failed.includes("pay") && !failed.includes("cash"),
            "Printer failure must not silently charge customer or deduct stock");
    }
    console.log("Restaurant cash/card/Kaspi checkout print gate passed");
})().catch(err=>{console.error(err);process.exitCode=1});
