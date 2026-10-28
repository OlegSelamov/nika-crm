// Run the real payExistingFoodOrder() handler with mocked payment providers.
// Electron requires BOTH restaurant receipts before payment.
// Web checkout saves and may preview receipts, never requires a local printer.
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const path = require("node:path");
const src = fs.readFileSync(path.join(__dirname, "../static/js/food_sales.js"), "utf8");
const start = src.indexOf("    async function finalizeFoodPaymentAfterChecks(");
const end = src.indexOf("\n    function newFoodOrder()", start);
assert.ok(start >= 0 && end > start, "Could not locate checkout functions");
const functionCode = src.slice(start, end);

async function checkout(method, {alreadyPrinted=false, printOK=true, stockAllowed=true, runtime="electron",autoPrint=true}={}) {
    const calls = [];
    const button = {disabled:false};
    const values = {
        cardInput: method === "card" ? "1000" : "",
        kaspiInput: method === "kaspi" ? "1000" : "",
        cashReceivedInput: "1100"
    };
    const sandbox = {
        getCart:()=>[{id:1,qty:1,price:1000}],
        window:{
            nikaKaspiPosActive:false,
            nikaConfirmNegativeStockSale:async()=>{
                calls.push("stock");
                return stockAllowed;
            }
        },
        foodCheckoutBusy:false,
        pendingFoodCashConfirmation:false,
        currentMode:()=>"food",
        document:{getElementById:(id)=>id==="foodCompletePayment"||id==="cashChangeConfirm"
            ? button:{value:values[id]||""}},
        foodMessage:(msg)=>calls.push("message:"+msg),
        showFoodPrintStatus:()=>{},
        isFoodTicketCurrent:()=>alreadyPrinted,
        isElectronFoodCheckout:()=>runtime==="electron",
        foodAutoPrintPreference:async()=>autoPrint,
        currentFoodOrderId:42,
        openFoodTicketPair:(id)=>calls.push("preview:"+id),
        saveFoodOrder:async()=>{calls.push("save");return {id:42};},
        printBothFoodTickets:async()=>{calls.push("print");return printOK;},
        openCashChangeModal:()=>calls.push("cash-modal"),
        renderCashChange:()=>{},
        closeCashChangeModal:()=>calls.push("cash-close"),
        selectedFoodPaymentMethod:()=>method,
        submitSalePayment:async(options)=>{
            assert.equal(options.paymentMethod,method);
            assert.equal(options.cash,method==="cash"?1100:0);
            assert.equal(options.cashChange,method==="cash"?100:0);
            assert.equal(options.card,method==="card"?1000:0);
            assert.equal(options.kaspi,method==="kaspi"?1000:0);
            calls.push("submit:"+method);
            return true;
        },
        console
    };
    vm.runInNewContext(functionCode+
        "\nthis.handler=payExistingFoodOrder;this.cashHandler=confirmFoodCashPayment;",sandbox);
    await sandbox.handler();
    if(method==="cash" && calls.includes("cash-modal")) {
        await sandbox.cashHandler({preventDefault(){},stopImmediatePropagation(){}});
    }
    assert.equal(button.disabled,false);
    return calls;
}


// Also exercise the dedicated GREEN button, independently from the blue
// confirmation button. Previous regressions covered only payment confirmation.
const greenStart=src.indexOf("    async function createFoodPrecheck() {");
const greenEnd=src.indexOf("\n    async function payExistingFoodOrder()",greenStart);
assert.ok(greenStart>=0&&greenEnd>greenStart,"Green precheck handler missing");
const greenCode=src.slice(greenStart,greenEnd);

async function printFromGreenButton(method,fail=false,autoPrint=true,runtime="electron"){
    const calls=[];
    const button={disabled:false};
    const sb={
        foodCheckoutBusy:false,
        getCart:()=>[{id:1,qty:1}],
        document:{getElementById:()=>button},
        showFoodPrintStatus:msg=>calls.push("clear:"+msg),
        foodMessage:()=>{},
        isElectronFoodCheckout:()=>runtime==="electron",
        foodAutoPrintPreference:async()=>autoPrint,
        openFoodTicketPair:()=>calls.push("preview:"+method),
        saveFoodOrder:async()=>{calls.push("save:"+method);return {id:123};},
        printBothFoodTickets:async()=>{calls.push("dual:"+method);return !fail;},
        console
    };
    vm.runInNewContext(greenCode+"\nthis.handler=createFoodPrecheck;",sb);
    await sb.handler();
    assert.equal(button.disabled,false);
    if (calls.includes("dual:"+method)) {
        assert.ok(calls.indexOf("save:"+method)<calls.indexOf("dual:"+method),
            "Save must happen before printing on green button");
    }
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


const foodPrintStart=src.indexOf("    async function printBothFoodTickets(");
const foodPrintEnd=src.indexOf("\n    async function createFoodPrecheck()",foodPrintStart);
assert.ok(foodPrintStart>=0&&foodPrintEnd>foodPrintStart,"Food receipt batch handler not found");
async function testElectronPreviewBeforeSpool() {
    const actions=[];
    const printer={
        printFoodOrder:async()=>{
            actions.push("spool");
            return {success:true,guest:{success:true},kitchen:{success:true}};
        }
    };
    const ctx={
        getFoodPrinterBridge:()=>printer,
        isElectronFoodCheckout:()=>true,
        savedFoodTicketFingerprint:()=>"fingerprint",
        currentFoodUiSignature:()=>"ui-state",
        getSavedFoodTicketHtml:async(_id,kind)=>"<main>"+kind+"</main>",
        openFoodTicketPair:async(_id,options)=>{
            assert.equal(options.cashReceived,1100);
            assert.equal(options.waitForPreview,true);
            actions.push("preview");
        },
        setFoodPairAutoPrinting:busy=>actions.push(busy?"disable-manual":"enable-manual"),
        foodCashPrintReceived:1100,
        lastFoodPrintFingerprint:null,
        lastFoodPrintUiSignature:null,
        showFoodPrintStatus:()=>{},
        foodMessage:()=>{},
        console
    };
    vm.runInNewContext(src.slice(foodPrintStart,foodPrintEnd)+
        "\nthis.printPair=printBothFoodTickets;",ctx);
    const result=await ctx.printPair({id:42,cart:[],planned_payment_method:"cash"});
    assert.equal(result,true);
    assert.deepEqual(actions,["disable-manual","preview","spool","enable-manual"]);
}

(async()=>{
    await testElectronPreviewBeforeSpool();
    for(const method of ["cash","card","kaspi"]) {
        const first=await checkout(method);
        assert.deepEqual(first,method==="cash"
            ? ["stock","cash-modal","save","print","submit:cash","cash-close"]
            : ["stock","save","print","submit:"+method],
            "Confirm must check stock and cash before printing for "+method);
        const already=await checkout(method,{alreadyPrinted:true});
        assert.deepEqual(already,method==="cash"
            ? ["stock","cash-modal","submit:cash","cash-close"]
            : ["stock","submit:"+method],
            "Preprinted order must not print again for "+method);
        const failed=await checkout(method,{printOK:false});
        assert.ok(failed.includes("save")&&failed.includes("print"));
        assert.ok(!failed.includes("submit:"+method),"Printer failure must block payment");
        const off=await checkout(method,{autoPrint:false});
        assert.deepEqual(off.filter(x=>!x.startsWith("message:")),method==="cash"
            ? ["stock","cash-modal","save","submit:cash","preview:42","cash-close"]
            : ["stock","save","submit:"+method,"preview:42"],
            "Disabled auto-print must save, pay and open preview without printing for "+method);
        const unknown=await checkout(method,{autoPrint:null});
        assert.deepEqual(unknown.filter(x=>!x.startsWith("message:")),
            off.filter(x=>!x.startsWith("message:")),
            "Missing printer settings must never force printing");
        const noAuto=await checkout(method,{autoPrint:false,printOK:false});
        assert.ok(noAuto.includes("preview:42"),
            "Auto-print disabled Electron must preview the two tickets after payment");
        const website=await checkout(method,{runtime:"website",printOK:false});
        assert.deepEqual(website,method==="cash"
            ? ["stock","cash-modal","save","submit:cash","preview:42","cash-close"]
            : ["stock","save","submit:"+method,"preview:42"],
            "Browser must complete "+method+" without printer or false printing errors");
        const websiteSaved=await checkout(method,{runtime:"website",alreadyPrinted:true});
        assert.deepEqual(websiteSaved,method==="cash"
            ? ["stock","cash-modal","submit:cash","cash-close"]
            : ["stock","submit:"+method],
            "Existing browser precheck must not create another sale or receipt");
        const stockDenied=await checkout(method,{stockAllowed:false});
        assert.deepEqual(stockDenied,["stock"],"Declined stock warning must not print or charge");
    }
    for(const method of ["cash","card","kaspi"]) {
        const off=await printFromGreenButton(method,false,false);
        assert.deepEqual(off,["save:"+method,"preview:"+method],
            "Green checkout must preview but not print when disabled");
        const unknown=await printFromGreenButton(method,false,null);
        assert.deepEqual(unknown,["save:"+method,"preview:"+method],
            "Green checkout must preview but not print on unknown setting");
        const browser=await printFromGreenButton(method,false,false,"website");
        assert.ok(browser.includes("dual:"+method),"Browser preview must stay available");
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
    console.log("Food auto-print on/off and browser receipt flow passed");
})().catch(err=>{console.error(err);process.exitCode=1});
