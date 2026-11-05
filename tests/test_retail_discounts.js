// Pure retail checkout regression tests: no browser, DB, or fiscal API calls.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('static/js/sales.js', 'utf8');

function section(start, end) {
  const a = source.indexOf(start), b = source.indexOf(end, a + start.length);
  assert(a !== -1 && b > a, 'Missing checkout helper: ' + start);
  return source.slice(a, b);
}
const discountHelpers = section('function nikaSaleDiscountPercent(', 'function selectItemForSale(');
const discountUi = section('function changeCartDiscountKind()', 'function importStorefrontOrderToSales(');
const input = {value: '50'};
const error = {textContent: ''};
const context = {
  Math, Number, isFinite, console,
  cart: [],
  salesDiscountTargetIndex: null,
  salePaymentBusy: false,
  window: {nikaKaspiPosActive: false},
  document: {
    getElementById(id) {
      return id === 'salesDiscountPercent' ? input :
        id === 'salesDiscountError' ? error : null;
    },
    querySelector() { return {value: context.mode}; },
  },
  closeCartDiscount() {},
  renderCart() {},
  saleMoney(value) { return value + ' ₸'; },
  isVariableQuantityUnit(unit) { return ['кг', 'л', 'час'].includes(unit); },
};
vm.createContext(context);
vm.runInContext(discountHelpers + '\n' + discountUi, context);
function applyDiscount(mode, amount, index=null) {
  context.mode = mode;
  input.value = String(amount);
  context.salesDiscountTargetIndex = index;
  error.textContent = '';
  vm.runInContext('applyCartDiscount()', context);
  assert.equal(error.textContent, '');
}
context.cart = [
  {id: 1, name: 'Товар', base_price: 1000, price: 1000, qty: 3, unit: 'шт'},
];
applyDiscount('amount', 50, 0);
assert.equal(context.cart[0].line_total, 2950);
assert.equal(context.cart[0].discount_amount, 50);
assert.equal(context.cart[0].price, 983.33);
assert.equal(context.cart[0].discount_type, 'amount');
applyDiscount('percent', 10, 0);
assert.equal(context.cart[0].price, 900);
assert.equal(context.cart[0].line_total, undefined);
assert.equal(context.cart[0].discount_type, 'percent');
context.cart = [
  {id: 1, price: 1000, qty: 1, unit: 'шт'},
  {id: 2, price: 2000, qty: 1, unit: 'шт'},
];
applyDiscount('amount', 600);
assert.equal(context.cart.reduce((sum, item) => sum + item.line_total, 0), 2400);
assert.equal(context.cart.reduce((sum, item) => sum + item.discount_amount, 0), 600);
input.value = '4000';
context.mode = 'amount';
vm.runInContext('applyCartDiscount()', context);
assert.match(error.textContent, /больше стоимости/);
console.log('Retail discount browser checkout tests: OK');
