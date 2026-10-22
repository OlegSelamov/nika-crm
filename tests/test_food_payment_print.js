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


// Also exercise the dedicated GREEN button, independently from the blue
// confirmation button. Previous regressions covered only payment confirmation.
const greenStart=src.indexOf("    async function createFoodPrecheck() {");
const greenEnd=src.indexOf("\n    async function payExistingFoodOrder()",greenStart);
assert.ok(greenStart>=0&&greenEnd>greenStart,"Green precheck handler missing");
const greenCode=src.slice(greenStart,greenEnd);

async function printFromGreenButton(method,fail=false){
    const calls=[];
    const button={disabled:false};
    const sb={
        foodCheckoutBusy:false,
        getCart:()=>[{id:1,qty:1}],
        document:{getElementById:()=>button},
        showFoodPrintStatus:msg=>calls.push("clear:"+msg),
        foodMessage:()=>{},
        saveFoodOrder:async()=>{calls.push("save:"+method);return {id:123};},
        printBothFoodTickets:async()=>{calls.push("dual:"+method);return !fail;},
        console
    };
    vm.runInNewContext(greenCode+"\nthis.handler=createFoodPrecheck;",sb);
    await sb.handler();
    assert.equal(button.disabled,false);
    assert.ok(calls.indexOf("save:"+method)<calls.indexOf("dual:"+method),
        "Save must happen before printing on green button");
    return calls;
}

// Exercise the real common payment function, verifying FOOD print suppression
// and that RETAIL still auto-prints the original receipt.
const saleSource=fs.readFileSync(path.join(__dirname,"../static/js/sales.js"),"utf8");
const saleStart=saleSource.indexOf("async function submitSalePayment({");
const saleEnd=saleSource.indexOf("\nlet itemSearchController",saleStart);
assert.ok(saleStart>=0&&saleEnd>saleStart,"Sale payment function missing");
const saleCode=saleSource.slice(saleStart,saleEnd);

async function simulateSale(method,mode,result){
    const calls=[];
    const food=mode==="foodservice";
    const sb={
        salePaymentBusy:false,
        renderCashChange:()=>{},
        selectedClient:1,
        cart:[{id:5,qty:1}],
        window:{
            NIKA_BUSINESS_MODE:mode,
            lastKaspiTransactionId:"",
            lastKaspiMethod:"",
            NikaFoodSales:{
                getSavedOrderId:()=>123,
                paymentNotice:()=>calls.push("notice")
            },
            dispatchEvent:()=>calls.push("event")
        },
        document:{getElementById:()=>({value:""})},
        fetch:async(_url,options)=>{
            const body=JSON.parse(options.body);
            assert.equal(body.food_mode,food);
            assert.equal(body.payment_method,method);
            return {ok:true,json:async()=>result};
        },
        CustomEvent:function(){},
        renderCart:()=>{},
        resetSaleAmounts:()=>{},
        closeCashChangeModal:()=>{},
        showCashChangeNotice:()=>{},
        openSaleModal:()=>calls.push("THIRD_RECEIPT"),
        alert:()=>calls.push("alert"),
        console
    };
    vm.runInNewContext(saleCode+"\nthis.submit=submitSalePayment;",sb);
    assert.equal(await sb.submit({paymentMethod:method,cash:method==="cash"?1000:0,
        card:method==="card"?1000:0,kaspi:method==="kaspi"?1000:0,cashChange:0}),true);
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
    for(const method of ["cash","card","kaspi"]) {
        const green=await printFromGreenButton(method);
        assert.ok(green.includes("dual:"+method),"Green button must print for "+method);
        const noKkm={success:true,sale_id:22,fiscalized:false,fiscalization_skipped:true};
        const foodCalls=await simulateSale(method,"foodservice",noKkm);
        assert.ok(!foodCalls.includes("THIRD_RECEIPT"),
            "Do not print a pretend fiscal receipt for "+method);
        assert.ok(foodCalls.includes("notice"));
        const retailCalls=await simulateSale(method,"retail",noKkm);
        assert.ok(retailCalls.includes("THIRD_RECEIPT"),
            "Retail must retain its regular payment receipt behavior");
        const phantom=await simulateSale(method,"foodservice",{
            success:true,sale_id:22,fiscalized:true,fiscalization_skipped:false,
            fiscal:{ticket_id:null,ticket_number:null}
        });
        assert.ok(!phantom.includes("THIRD_RECEIPT"),"Fiscal flag alone is not a receipt");
        const real=await simulateSale(method,"foodservice",{
            success:true,sale_id:22,fiscalized:true,fiscalization_skipped:false,
            fiscal:{ticket_id:"R-123",ticket_number:"T-123"}
        });
        assert.ok(real.includes("THIRD_RECEIPT"),"Real fiscal ticket should still be printed");
    }
    console.log("Restaurant cash/card/Kaspi green prechecks and fiscal/nonfiscal printing passed");
})().catch(err=>{console.error(err);process.exitCode=1});
