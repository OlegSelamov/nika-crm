"use strict";
// Behavior tests for the real tab logic; no network or browser dependencies.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "static/js/food_sales.js"), "utf8");
const tabStart = source.indexOf("    function setFoodModifierTab(tabName) {");
const modalStart = source.indexOf("    function openFoodModifierModal(", tabStart);
const helperStart = source.indexOf("    function escapeFood(v)", modalStart);
const closeStart = source.indexOf("    function closeFoodModifierModal()", helperStart);
assert(tabStart >= 0 && modalStart > tabStart && closeStart > helperStart, "Modifier UI not found");

const createTab = () => ({
    attrs: {}, classes: new Set(), tabIndex: 0,
    classList: {toggle(name, value) { if (value) this.parent.classes.add(name); else this.parent.classes.delete(name); }},
    setAttribute(name, value) { this.attrs[name] = value; }
});
const addTab = createTab(), removeTab = createTab();
addTab.classList.parent = addTab;
removeTab.classList.parent = removeTab;

const panes = {
    foodModifierGroups: {hidden: false},
    foodModifierExclusions: {hidden: true}
};
const addBadge = {hidden: true, textContent: "0"};
const removeBadge = {hidden: true, textContent: "0"};
const total = {textContent: ""};
const elements = {
    foodModifierAddTab: addTab,
    foodModifierRemoveTab: removeTab,
    foodModifierGroups: panes.foodModifierGroups,
    foodModifierExclusions: panes.foodModifierExclusions,
    foodModifierAddCount: addBadge,
    foodModifierRemoveCount: removeBadge,
    foodModifierTotal: total
};
const addInputs = [{value: "22", dataset: {groupId: "7"}, checked: true}];
const removeInputs = [{dataset: {excludedIngredientId: "101"}, checked: true}];
const document = {
    getElementById(id) { return elements[id] || null; },
    querySelectorAll(selector) {
        if (selector === "#foodModifierGroups input:checked") return addInputs.filter(input => input.checked);
        if (selector === "#foodModifierExclusions input:checked") return removeInputs.filter(input => input.checked);
        throw Error("Unexpected selector: " + selector);
    }
};
const ctx = {
    document,
    money: n => n + " ₸",
    pendingModifierItem: {retail_price: 1200},
    pendingModifierGroups: [{id: 7, options: [{id: 22, name: "Сыр", price_delta: 250}]}]
};
const api = vm.runInNewContext(
    source.slice(tabStart, modalStart) + "\n" +
    source.slice(helperStart, closeStart) + "\n" +
    "({setFoodModifierTab, updateFoodModifierTabCounts, selectedFoodModifiers, renderFoodModifierTotal})",
    ctx
);

// Added options change price; excluded ingredients do not.
api.setFoodModifierTab("add");
assert.equal(panes.foodModifierGroups.hidden, false);
assert.equal(panes.foodModifierExclusions.hidden, true);
assert.equal(addTab.attrs["aria-selected"], "true");
api.renderFoodModifierTotal();
assert.equal(total.textContent, "1450 ₸");
assert.equal(addBadge.textContent, "1");
assert.equal(removeBadge.textContent, "1");
assert.equal(addBadge.hidden, false);
assert.equal(removeBadge.hidden, false);
assert.deepEqual(Array.from(api.selectedFoodModifiers(), x => x.id), [22]);

api.setFoodModifierTab("remove");
assert.equal(panes.foodModifierGroups.hidden, true);
assert.equal(panes.foodModifierExclusions.hidden, false);
assert.equal(removeTab.attrs["aria-selected"], "true");
assert.equal(addTab.tabIndex, -1);
assert.equal(removeTab.tabIndex, 0);
assert.equal(addInputs[0].checked, true, "Switching tabs must keep additions");
assert.equal(removeInputs[0].checked, true, "Switching tabs must keep exclusions");
api.renderFoodModifierTotal();
assert.equal(total.textContent, "1450 ₸", "Removing ingredients must not change price");

removeInputs[0].checked = false;
api.updateFoodModifierTabCounts();
assert.equal(removeBadge.hidden, true);
assert.equal(addBadge.textContent, "1");

api.setFoodModifierTab("add");
addInputs[0].checked = false;
api.renderFoodModifierTotal();
assert.equal(total.textContent, "1200 ₸");
assert.equal(addBadge.hidden, true);
console.log("Food modifier tab behavior: selection persistence, badges and pricing passed");
