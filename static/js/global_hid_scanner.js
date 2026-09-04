(function () {
    const path = window.location.pathname.replace(/\/+$/, '') || '/';

    // Продажи имеют специальный обработчик: там скан сразу добавляет товар в корзину.
    if (path === '/sales') return;

    const supported =
        path === '/items' ||
        path === '/stock' ||
        path === '/stock/income' ||
        path === '/stock/writeoff' ||
        path === '/stock/movements' ||
        path === '/clients';

    if (!supported) return;

    const MIN_LENGTH = 8;
    const MAX_GAP_MS = 140;
    const FINISH_DELAY_MS = 170;
    const SUFFIX_GUARD_MS = 500;

    let buffer = '';
    let startedAt = 0;
    let lastKeyAt = 0;
    let finishTimer = null;
    let recentScanAt = 0;
    let sourceElement = null;
    let sourceSnapshot = null;

    function clearTimer() {
        if (finishTimer) clearTimeout(finishTimer);
        finishTimer = null;
    }

    function reset() {
        clearTimer();
        buffer = '';
        startedAt = 0;
        lastKeyAt = 0;
        sourceElement = null;
        sourceSnapshot = null;
    }

    function snapshotEditable(target) {
        if (!target) return null;
        const tag = String(target.tagName || '').toLowerCase();
        if (!['input', 'textarea'].includes(tag) || target.readOnly || target.disabled) return null;
        return {
            value: target.value,
            selectionStart: typeof target.selectionStart === 'number' ? target.selectionStart : null,
            selectionEnd: typeof target.selectionEnd === 'number' ? target.selectionEnd : null
        };
    }

    function restoreSourceInput() {
        if (!sourceElement || !sourceSnapshot || !document.contains(sourceElement)) return;
        sourceElement.value = sourceSnapshot.value;
        try {
            if (sourceSnapshot.selectionStart !== null) {
                sourceElement.setSelectionRange(sourceSnapshot.selectionStart, sourceSnapshot.selectionEnd);
            }
        } catch (_) {}
        sourceElement.dispatchEvent(new Event('input', {bubbles: true}));
    }

    function setSearchValue(id, value, directCallback) {
        const input = document.getElementById(id);
        if (!input) return false;
        input.value = value;
        input.dispatchEvent(new Event('input', {bubbles: true}));
        if (typeof directCallback === 'function') directCallback();
        return true;
    }

    async function resolveStockItem(code) {
        try {
            const params = new URLSearchParams({
                q: code,
                limit: '30',
                offset: '0',
                sort: 'name'
            });
            const response = await fetch('/api/stock?' + params.toString(), {
                headers: {'Accept': 'application/json'}
            });
            if (!response.ok) return null;
            const data = await response.json();
            const items = Array.isArray(data.items) ? data.items : [];
            const normalized = String(code).trim().toLowerCase();
            return items.find(item =>
                [item.barcode, item.gtin, item.ntin]
                    .some(value => String(value || '').trim().toLowerCase() === normalized)
            ) || items[0] || null;
        } catch (error) {
            console.error('Global scanner stock lookup failed:', error);
            return null;
        }
    }

    async function routeScan(code) {
        if (path === '/items') {
            setSearchValue('catalogSearch', code, function () {
                if (typeof window.filterCatalogItems === 'function') window.filterCatalogItems();
            });
            return;
        }

        if (path === '/stock') {
            setSearchValue('stockSearch', code, function () {
                if (typeof window.loadStock === 'function') window.loadStock();
            });
            return;
        }

        if (path === '/stock/income') {
            setSearchValue('incomeProductSearch', code);
            return;
        }

        if (path === '/stock/writeoff') {
            setSearchValue('writeoffProductSearch', code);
            return;
        }

        if (path === '/stock/movements') {
            const item = await resolveStockItem(code);
            const query = item && item.name ? item.name : code;
            setSearchValue('movementSearch', query, function () {
                if (typeof window.applyMovementFilters === 'function') window.applyMovementFilters();
            });
            return;
        }

        if (path === '/clients') {
            setSearchValue('clientSearch', code, function () {
                if (typeof window.filterClients === 'function') window.filterClients();
            });
        }
    }

    function finishScan() {
        clearTimer();

        const code = buffer.trim();
        const duration = startedAt && lastKeyAt ? Math.max(0, lastKeyAt - startedAt) : 0;
        const avgGap = code.length > 1 ? duration / (code.length - 1) : Infinity;
        const looksLikeScanner =
            code.length >= MIN_LENGTH &&
            (avgGap <= MAX_GAP_MS || duration <= 950);

        if (!looksLikeScanner) {
            reset();
            return false;
        }

        // Если скан начался, когда курсор стоял, например, в количестве или
        // комментарии, возвращаем ручное значение поля и направляем код туда,
        // куда он должен попасть на текущей странице.
        restoreSourceInput();

        recentScanAt = Date.now();
        const finalCode = code;
        reset();
        routeScan(finalCode);
        return true;
    }

    function scheduleFinish() {
        clearTimer();
        finishTimer = setTimeout(finishScan, FINISH_DELAY_MS);
    }

    document.addEventListener('keydown', function (event) {
        if (event.ctrlKey || event.altKey || event.metaKey) return;

        const now = Date.now();
        const key = event.key;

        if (key === 'Enter' || key === 'Tab') {
            if (buffer.length >= MIN_LENGTH) {
                const recognized = finishScan();
                if (recognized) {
                    event.preventDefault();
                    event.stopImmediatePropagation();
                }
                return;
            }

            if (now - recentScanAt < SUFFIX_GUARD_MS) {
                event.preventDefault();
                event.stopImmediatePropagation();
            }
            return;
        }

        if (key.length !== 1 || /\s/.test(key)) return;

        if (!lastKeyAt || now - lastKeyAt > MAX_GAP_MS) {
            buffer = '';
            startedAt = now;
            sourceElement = event.target;
            sourceSnapshot = snapshotEditable(event.target);
        }

        if (!buffer) {
            startedAt = now;
            sourceElement = event.target;
            sourceSnapshot = snapshotEditable(event.target);
        }

        buffer += key;
        lastKeyAt = now;
        scheduleFinish();
    }, true);
})();
