(function () {
    var state = {
        calculatedField: null,
        unlocked: false
    };

    function isCatalogPriceForm() {
        return Boolean(document.getElementById('itemPurchasePrice') && document.getElementById('itemRetailPrice'));
    }

    function selectedItemType() {
        var selected = document.querySelector('input[name="item_type"]:checked');
        return selected ? selected.value : 'product';
    }

    function isProduct() {
        return selectedItemType() !== 'service';
    }

    function fieldFor(name) {
        return document.getElementById(name === 'purchase' ? 'itemPurchasePrice' : 'itemRetailPrice');
    }

    function buttonFor(name) {
        return document.getElementById(name === 'purchase' ? 'itemPurchasePriceLock' : 'itemRetailPriceLock');
    }

    function clearCalculatedField() {
        state.calculatedField = null;
        state.unlocked = false;
        syncPriceLocks();
    }

    function setCalculatedField(name) {
        state.calculatedField = name;
        state.unlocked = false;
        syncPriceLocks();
    }

    function syncPriceLocks() {
        ['purchase', 'retail'].forEach(function (name) {
            var field = fieldFor(name);
            var button = buttonFor(name);
            if (!field || !button) return;

            var active = isProduct() && state.calculatedField === name;
            button.hidden = !active;
            field.readOnly = active && !state.unlocked;
            field.classList.toggle('nika-price-calculated', active && !state.unlocked);

            if (active) {
                button.textContent = state.unlocked ? '🔓' : '🔒';
                button.title = state.unlocked
                    ? 'Цена доступна для ручной правки. Нажмите, чтобы снова зафиксировать.'
                    : 'Цена рассчитана автоматически. Нажмите, чтобы исправить вручную.';
                button.setAttribute('aria-label', button.title);
                button.classList.toggle('is-unlocked', state.unlocked);
            } else {
                button.classList.remove('is-unlocked');
            }
        });
    }

    function toggleCalculatedField(name) {
        if (state.calculatedField !== name || !isProduct()) return;
        state.unlocked = !state.unlocked;
        syncPriceLocks();
        if (state.unlocked) {
            var field = fieldFor(name);
            if (field) {
                field.focus();
                field.select();
            }
        }
    }

    function injectPriceLockStyles() {
        if (document.getElementById('nikaCatalogPriceLockStyles')) return;
        var style = document.createElement('style');
        style.id = 'nikaCatalogPriceLockStyles';
        style.textContent = [
            '.nika-price-lock-wrap{display:flex;align-items:center;gap:8px;width:100%;}',
            '.nika-price-lock-wrap>input{flex:1;min-width:0;}',
            '.nika-price-lock-btn{width:42px;height:42px;flex:0 0 42px;border:1px solid rgba(45,108,223,.24);border-radius:10px;background:#eef4ff;cursor:pointer;font-size:18px;line-height:1;display:flex;align-items:center;justify-content:center;transition:.15s ease;}',
            '.nika-price-lock-btn:hover{background:#e1ecff;transform:translateY(-1px);}',
            '.nika-price-lock-btn.is-unlocked{background:#f4f7fb;border-color:#d8e0eb;}',
            '.nika-price-calculated{background:#f6f8fb!important;color:#526174;}',
            '.nika-price-lock-btn[hidden]{display:none!important;}'
        ].join('');
        document.head.appendChild(style);
    }

    function addLockButton(fieldName, id) {
        var field = fieldFor(fieldName);
        if (!field || document.getElementById(id)) return;

        var parent = field.parentNode;
        var wrap = document.createElement('div');
        wrap.className = 'nika-price-lock-wrap';
        parent.insertBefore(wrap, field);
        wrap.appendChild(field);

        var button = document.createElement('button');
        button.type = 'button';
        button.id = id;
        button.className = 'nika-price-lock-btn';
        button.hidden = true;
        button.textContent = '🔒';
        button.addEventListener('click', function () {
            toggleCalculatedField(fieldName);
        });
        wrap.appendChild(button);
    }

    function installControls() {
        if (!isCatalogPriceForm()) return false;
        injectPriceLockStyles();
        addLockButton('purchase', 'itemPurchasePriceLock');
        addLockButton('retail', 'itemRetailPriceLock');
        syncPriceLocks();
        return true;
    }

    function currentMarkup() {
        if (typeof window.getSelectedCategoryMarkup === 'function') {
            return Number(window.getSelectedCategoryMarkup()) || 0;
        }
        return 0;
    }

    function rounded(value) {
        return Math.ceil(Number(value) || 0);
    }

    function calculatePurchasePriceLocked() {
        if (!isProduct()) return;
        var retail = fieldFor('retail');
        var purchase = fieldFor('purchase');
        if (!retail || !purchase) return;

        var value = parseFloat(retail.value) || 0;
        if (value <= 0) {
            purchase.value = '';
            clearCalculatedField();
            return;
        }

        var divisor = 1 + currentMarkup() / 100;
        purchase.value = rounded(divisor > 0 ? value / divisor : value);
        setCalculatedField('purchase');
    }

    function calculateRetailPriceLocked() {
        if (!isProduct()) return;
        var retail = fieldFor('retail');
        var purchase = fieldFor('purchase');
        if (!retail || !purchase) return;

        var value = parseFloat(purchase.value) || 0;
        if (value <= 0) {
            retail.value = '';
            clearCalculatedField();
            return;
        }

        retail.value = rounded(value * (1 + currentMarkup() / 100));
        setCalculatedField('retail');
    }

    function recalculateLockedPrice() {
        if (!isProduct() || state.unlocked) return;
        if (state.calculatedField === 'purchase') {
            calculatePurchasePriceLocked();
            return;
        }
        if (state.calculatedField === 'retail') {
            calculateRetailPriceLocked();
            return;
        }

        if (window.priceCalculationSource === 'retail') {
            calculatePurchasePriceLocked();
        } else {
            calculateRetailPriceLocked();
        }
    }

    function resetPriceLockState() {
        state.calculatedField = null;
        state.unlocked = false;
        window.setTimeout(syncPriceLocks, 0);
    }

    function wrapModalFunction(name) {
        var original = window[name];
        if (typeof original !== 'function' || original.__nikaPriceLockWrapped) return;
        var wrapped = function () {
            resetPriceLockState();
            var result = original.apply(this, arguments);
            window.setTimeout(function () {
                installControls();
                resetPriceLockState();
            }, 0);
            return result;
        };
        wrapped.__nikaPriceLockWrapped = true;
        window[name] = wrapped;
    }

    function installOverrides() {
        if (!installControls()) return;

        window.calculatePurchasePrice = calculatePurchasePriceLocked;
        window.calculateRetailPrice = calculateRetailPriceLocked;
        window.recalculatePricesByLastSource = recalculateLockedPrice;

        wrapModalFunction('openAddItemModal');
        wrapModalFunction('openEditItemModal');
    }

    document.addEventListener('input', function (event) {
        var target = event.target;
        if (!target || !isProduct() || !state.unlocked) return;

        if (state.calculatedField === 'purchase' && target.id === 'itemPurchasePrice') {
            event.stopImmediatePropagation();
        } else if (state.calculatedField === 'retail' && target.id === 'itemRetailPrice') {
            event.stopImmediatePropagation();
        }
    }, true);

    document.addEventListener('change', function (event) {
        if (!event.target || event.target.name !== 'item_type') return;
        if (!isProduct()) {
            clearCalculatedField();
        } else {
            syncPriceLocks();
        }
    });

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', installOverrides);
    } else {
        installOverrides();
    }
})();
