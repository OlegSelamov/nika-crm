(function () {
    if (!window.location.pathname.startsWith('/sales')) return;

    // Quick-add modal fixes live separately so the main sales.js can stay stable.
    if (!document.querySelector('link[href*="sales_quick_add.css"]')) {
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = '/static/css/sales_quick_add.css?v=20260904-1';
        document.head.appendChild(link);
    }
    if (!document.querySelector('script[src*="sales_quick_add.js"]')) {
        const script = document.createElement('script');
        script.src = '/static/js/sales_quick_add.js?v=20260904-1';
        script.defer = true;
        document.body.appendChild(script);
    }

    const searchInput = document.getElementById('search');
    if (!searchInput || typeof handleBarcode !== 'function') return;

    // Продажи раньше использовали старый /api/items/search, который не отдавал
    // фото. Переключаем ручной поиск на тот же API, что использует Каталог:
    // он возвращает первое изображение из item_images и одинаково работает
    // для товаров и услуг.
    let salesCatalogSearchController = null;
    window.searchItems = async function (query) {
        if (salesCatalogSearchController) salesCatalogSearchController.abort();
        salesCatalogSearchController = new AbortController();

        try {
            const params = new URLSearchParams({
                q: String(query || '').trim(),
                type: 'all',
                category: 'all',
                page: '1',
                limit: '30'
            });

            const response = await fetch('/api/catalog/items?' + params.toString(), {
                signal: salesCatalogSearchController.signal,
                headers: {'Accept': 'application/json'}
            });

            if (!response.ok) throw new Error('HTTP ' + response.status);

            const data = await response.json();
            if (typeof window.renderItemSearchResults === 'function') {
                window.renderItemSearchResults(
                    Array.isArray(data.items) ? data.items : [],
                    Boolean(data.has_more)
                );
            }
        } catch (error) {
            if (error.name === 'AbortError') return;
            console.error('ITEM SEARCH ERROR:', error);
            const itemsList = document.getElementById('itemsList');
            if (itemsList) {
                itemsList.innerHTML = '<div class="items-search-message">Не удалось выполнить поиск</div>';
                itemsList.style.display = 'block';
            }
        }
    };

    const MIN_BARCODE_LENGTH = 8;
    const MAX_KEY_GAP_MS = 140;
    const AUTO_FINISH_DELAY_MS = 160;
    const RECENT_SCAN_GUARD_MS = 450;

    let buffer = '';
    let startedAt = 0;
    let lastKeyAt = 0;
    let finishTimer = null;
    let recentScanAt = 0;

    function clearFinishTimer() {
        if (finishTimer) {
            clearTimeout(finishTimer);
            finishTimer = null;
        }
    }

    function resetBuffer() {
        clearFinishTimer();
        buffer = '';
        startedAt = 0;
        lastKeyAt = 0;
    }

    function targetAllowsScanner(target) {
        if (!target) return true;
        if (target === searchInput) return true;

        const tag = String(target.tagName || '').toLowerCase();
        const editable =
            target.isContentEditable ||
            tag === 'input' ||
            tag === 'textarea' ||
            tag === 'select';

        return !editable;
    }

    function cancelNormalItemSearch() {
        try {
            if (typeof itemSearchTimer !== 'undefined') {
                clearTimeout(itemSearchTimer);
            }
        } catch (e) {}

        try {
            if (typeof itemSearchController !== 'undefined' && itemSearchController) {
                itemSearchController.abort();
            }
        } catch (e) {}

        try {
            if (salesCatalogSearchController) {
                salesCatalogSearchController.abort();
            }
        } catch (e) {}
    }

    function finishScan() {
        clearFinishTimer();

        const code = buffer.trim();
        const duration = startedAt && lastKeyAt ? Math.max(0, lastKeyAt - startedAt) : 0;
        const avgGap = code.length > 1 ? duration / (code.length - 1) : Infinity;

        const looksLikeScanner =
            code.length >= MIN_BARCODE_LENGTH &&
            (avgGap <= MAX_KEY_GAP_MS || duration <= 900);

        resetBuffer();

        if (!looksLikeScanner) return false;

        cancelNormalItemSearch();

        searchInput.value = '';
        const itemsBox = document.getElementById('itemsList');
        if (itemsBox) {
            itemsBox.innerHTML = '';
            itemsBox.style.display = 'none';
        }

        recentScanAt = Date.now();
        handleBarcode(code);
        return true;
    }

    function scheduleAutoFinish() {
        clearFinishTimer();
        finishTimer = setTimeout(() => {
            finishTimer = null;
            finishScan();
        }, AUTO_FINISH_DELAY_MS);
    }

    document.addEventListener('keydown', function (event) {
        if (event.ctrlKey || event.altKey || event.metaKey) return;

        const now = Date.now();
        const key = event.key;

        if (key === 'Enter' || key === 'Tab') {
            if (buffer.length >= MIN_BARCODE_LENGTH) {
                event.preventDefault();
                event.stopImmediatePropagation();
                finishScan();
                return;
            }

            if (now - recentScanAt < RECENT_SCAN_GUARD_MS) {
                event.preventDefault();
                event.stopImmediatePropagation();
            }
            return;
        }

        if (!targetAllowsScanner(event.target)) {
            resetBuffer();
            return;
        }

        if (key.length !== 1 || /\s/.test(key)) return;

        if (!lastKeyAt || now - lastKeyAt > MAX_KEY_GAP_MS) {
            buffer = '';
            startedAt = now;
        }

        if (!buffer) startedAt = now;
        buffer += key;
        lastKeyAt = now;

        scheduleAutoFinish();
    }, true);

    searchInput.addEventListener('input', function () {
        const value = String(searchInput.value || '').trim();
        if (value.length < MIN_BARCODE_LENGTH) return;

        if (!buffer && /^[0-9A-Za-z._\-/]+$/.test(value)) {
            buffer = value;
            startedAt = Date.now();
            lastKeyAt = startedAt;
            scheduleAutoFinish();
        }
    }, true);
})();
