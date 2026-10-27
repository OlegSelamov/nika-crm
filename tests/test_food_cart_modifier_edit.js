"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../static/js/food_sales.js"), "utf8");
const extract = (start, end) => {
    const from = source.indexOf(start);
    const to = source.indexOf(end, from + start.length);
    assert.ok(from >= 0 && to > from, "Missing handler: " + start);
    return source.slice(from, to);
};
const savedLine = {
    id: 19, name: "Шаурма", item_type: "dish", qty: 3,
    price: 2300, line_total: 6900,
    modifiers: [{id: 22, name: "Сыр", price_delta: 300}],
    excluded_ingredients: [{id: 101, name: "Лук"}],
};
const cart = [savedLine, {id: 21, item_type: "product", price: 100, qty: 1}];
const calls = [];
let opened = null;
const ctx = {
    foodOrderBusy: false, foodCheckoutBusy: false, foodChoiceRequest: 0,
    window: {nikaKaspiPosActive: false},
    currentMode: () => "food",
    getCart: () => cart,
    foodMessage: message => calls.push(message),
    fetch: async url => {
        calls.push(url);
        return {ok: true, json: async () => url.endsWith("modifiers")
            ? {success: true, groups: [{
                id: 7, name: "Дополнения", min_select: 0, max_select: 2,
                options: [{id: 22, name: "Сыр", price_delta: 300},
                          {id: 23, name: "Соус", price_delta: 100}]
            }]} : {success: true, ingredients: [{item_id: 101, name: "Лук"}]}};
    },
    openFoodModifierModal: (item, groups, ingredients, line) =>
        opened = {item, groups, ingredients, line},
};
const editCode = extract(
    "    function foodCartEditBasePrice(line) {",
    "    function setFoodModifierTab(tabName) {"
);
vm.runInNewContext(editCode + "\nthis.edit=editFoodCartItem;this.base=foodCartEditBasePrice", ctx);

function createElement() {
    const node = {
        children: [], checked: false, dataset: {}, hidden: false,
        append(...items) { this.children.push(...items); },
        appendChild(item) { this.children.push(item); },
        replaceChildren() { this.children = []; },
        addEventListener() {},
    };
    return node;
}

(async () => {
    assert.equal(ctx.base(savedLine), 2000);
    await ctx.edit(0);
    assert.equal(opened.item.retail_price, 2000,
        "Previously selected add-on must not be charged twice");
    assert.equal(opened.line, savedLine, "Must target the original cart line");
    assert.equal(savedLine.qty, 3);
    await ctx.edit(1);
    assert.equal(calls.filter(c => String(c).includes("/api/items/")).length, 2,
        "Retail item must not enter the restaurant modifier editor");

    const addRoot = createElement(), removeRoot = createElement();
    const modal = createElement(), submit = createElement();
    const body = {classList: {add() {}}};
    modal.parentElement = body;
    const nodes = {
        foodModifierModal: modal, foodModifierGroups: addRoot,
        foodModifierExclusions: removeRoot, foodModifierTitle: createElement(),
        foodModifierAdd: submit,
    };
    ctx.document = {
        body,
        getElementById: id => nodes[id],
        createElement,
    };
    ctx.setFoodModifierTab = () => {};
    ctx.renderFoodModifierTotal = () => {};
    ctx.updateFoodModifierTabCounts = () => {};
    ctx.escapeFood = value => String(value);
    ctx.money = value => String(value) + " ₸";
    const modalCode = extract(
        "    function openFoodModifierModal(item, groups, ingredients, editingLine = null) {",
        "    function escapeFood(v)"
    );
    vm.runInNewContext(modalCode + "\nthis.open=openFoodModifierModal", ctx);
    ctx.open(opened.item, opened.groups, opened.ingredients, savedLine);
    assert.equal(addRoot.children[1].children[0].children[0].checked, true,
        "Existing cheese option must be checked on reopening");
    assert.equal(removeRoot.children[1].children[0].children[0].checked, true,
        "Existing excluded onion must be checked on reopening");
    assert.equal(submit.textContent, "Сохранить изменения");
    ctx.open(opened.item, opened.groups, opened.ingredients);
    assert.equal(addRoot.children[1].children[0].children[0].checked, false,
        "A NEW dish must not inherit the previous selection");
    assert.equal(submit.textContent, "Добавить в заказ");

    ctx.pendingModifierItem = opened.item;
    ctx.pendingModifierGroups = opened.groups;
    ctx.pendingRecipeIngredients = opened.ingredients;
    ctx.pendingModifierCartLine = savedLine;
    ctx.selectedFoodModifiers = () => [{id: 23, name: "Соус", price_delta: 100}];
    ctx.document.querySelectorAll = selector =>
        selector.includes("data-group-id")
            ? [{checked: true}]
            : selector.includes("data-excluded-ingredient-id")
                ? [{dataset: {excludedIngredientId: "101"}}]
                : [];
    let rerenders = 0, printInvalidations = 0;
    ctx.renderCart = () => rerenders++;
    ctx.renderFoodCart = () => rerenders++;
    ctx.showFoodPrintStatus = () => printInvalidations++;
    ctx.closeFoodModifierModal = () => {};
    ctx.currentFoodOrderSaved = true;
    ctx.lastFoodPrintFingerprint = "old kitchen ticket";
    ctx.lastFoodPrintUiSignature = "old guest precheck";
    const confirmCode = extract(
        "    function confirmFoodModifiers(){",
        "    function makeFoodCard(item) {"
    );
    vm.runInNewContext(confirmCode + "\nthis.confirm=confirmFoodModifiers", ctx);
    ctx.confirm();
    assert.equal(cart.length, 2, "Edited line must not be added twice");
    assert.equal(savedLine.qty, 3, "Quantity must remain unchanged");
    assert.equal(savedLine.price, 2100, "Replace 300 cheese with 100 sauce");
    assert.equal(savedLine.line_total, undefined,
        "Cached total from the old modifiers must be removed");
    assert.equal(savedLine.modifiers[0].id, 23);
    assert.equal(savedLine.excluded_ingredients[0].id, 101);
    assert.equal(ctx.currentFoodOrderSaved, false);
    assert.equal(ctx.lastFoodPrintFingerprint, null);
    assert.equal(ctx.lastFoodPrintUiSignature, null);
    assert.equal(rerenders, 2);
    assert.equal(printInvalidations, 1);

    cart.shift(); // Item removed while editor is open.
    ctx.confirm();
    assert.equal(cart.length, 1, "Removed item must never reappear");
    console.log("Food cart modifier editing: selected choices, no duplicate prices/lines, quantity and stale precheck checks passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
