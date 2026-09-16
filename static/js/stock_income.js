document.addEventListener("DOMContentLoaded", function () {
    const SEARCH_DELAY = 300;
    const SEARCH_LIMIT = 30;

    const searchInput = document.getElementById("incomeProductSearch");
    const itemIdInput = document.getElementById("incomeItemId");
    const dropdown = document.getElementById("incomeProductList");
    const form = document.getElementById("incomeForm");

    const selectedBox = document.getElementById("selectedProduct");
    const selectedAvatar = document.getElementById("selectedProductAvatar");
    const selectedName = document.getElementById("selectedProductName");
    const selectedMeta = document.getElementById("selectedProductMeta");
    const clearSelected = document.getElementById("clearSelectedProduct");

    const quantityInput = document.getElementById("incomeQuantity");
    const priceInput = document.getElementById("incomePrice");
    const previousPriceHint = document.getElementById("previousPriceHint");
    const updateRetailInput = document.getElementById("incomeUpdateRetail");
    const retailHint = document.getElementById("incomeRetailHint");

    const summaryQuantity = document.getElementById("summaryQuantity");
    const summaryPrice = document.getElementById("summaryPrice");
    const summaryTotal = document.getElementById("summaryTotal");

    let highlightedIndex = -1;
    let searchTimer = null;
    let searchController = null;
    let selectedMarkup = 0;
    let selectedRetail = 0;

    function formatNumber(value, maximumFractionDigits = 3) {
        return new Intl.NumberFormat("ru-RU", {maximumFractionDigits})
            .format(Number(value || 0));
    }

    function formatMoney(value) {
        return new Intl.NumberFormat("ru-RU", {maximumFractionDigits: 2})
            .format(Number(value || 0)) + " ₸";
    }

    function updateRetailHint() {
        if (!updateRetailInput || !retailHint) return;

        const price = Number(priceInput?.value || 0);
        const canRecalculate = selectedMarkup > 0 && price > 0;
        updateRetailInput.disabled = !canRecalculate;

        if (selectedMarkup <= 0) {
            retailHint.textContent = itemIdInput?.value
                ? "У категории не указана наценка — розничная цена не изменится"
                : "Сначала выберите товар";
            return;
        }

        if (price <= 0) {
            retailHint.textContent = "Введите закупочную цену для расчёта";
            return;
        }

        const suggestedRetail = Math.ceil(price * (1 + selectedMarkup / 100));
        retailHint.textContent = `Текущая: ${formatMoney(selectedRetail)} → новая: ${formatMoney(suggestedRetail)} (наценка ${formatNumber(selectedMarkup, 2)}%)`;
    }

    function updateSummary() {
        const quantity = Number(quantityInput?.value || 0);
        const price = Number(priceInput?.value || 0);

        if (summaryQuantity) summaryQuantity.textContent = formatNumber(quantity);
        if (summaryPrice) summaryPrice.textContent = formatMoney(price);
        if (summaryTotal) summaryTotal.textContent = formatMoney(quantity * price);
    }

    function getOptions() {
        return Array.from(dropdown?.querySelectorAll(".product-option") || []);
    }

    function openDropdown() {
        dropdown?.classList.add("open");
    }

    function closeDropdown() {
        dropdown?.classList.remove("open");
        highlightedIndex = -1;
        getOptions().forEach(option => option.classList.remove("is-highlighted"));
    }

    function showMessage(title, text) {
        if (!dropdown) return;
        dropdown.replaceChildren();

        const message = document.createElement("div");
        message.className = "product-empty";

        const strong = document.createElement("strong");
        strong.textContent = title;
        const span = document.createElement("span");
        span.textContent = text;

        message.append(strong, span);
        dropdown.appendChild(message);
        highlightedIndex = -1;
        openDropdown();
    }

    function clearProduct({clearSearch = true} = {}) {
        if (itemIdInput) itemIdInput.value = "";
        if (searchInput) {
            if (clearSearch) searchInput.value = "";
            searchInput.setCustomValidity("");
        }
        if (selectedBox) selectedBox.hidden = true;
        selectedMarkup = 0;
        selectedRetail = 0;
        if (updateRetailInput) updateRetailInput.disabled = true;
        if (retailHint) retailHint.textContent = "Сначала выберите товар";
        if (previousPriceHint) {
            previousPriceHint.textContent = "После выбора товара подставится последняя закупочная цена";
        }
    }

    function selectProduct(option) {
        if (!option || !itemIdInput || !searchInput) return;

        const name = option.dataset.name || "";
        const unit = option.dataset.unit || "";
        const stock = option.dataset.stock || "0";
        const previousPrice = Number(option.dataset.lastPrice || option.dataset.price || 0);
        selectedMarkup = Number(option.dataset.markup || 0);
        selectedRetail = Number(option.dataset.retail || 0);

        itemIdInput.value = option.dataset.id || "";
        searchInput.value = name;
        searchInput.setCustomValidity("");

        if (selectedAvatar) selectedAvatar.replaceChildren();
        if (option.dataset.image) { const img = document.createElement("img"); img.src = option.dataset.image; img.alt = ""; selectedAvatar.appendChild(img); } else { selectedAvatar.textContent = (name || "Т").slice(0, 1).toUpperCase(); }
        if (selectedName) selectedName.textContent = name;
        if (selectedMeta) {
            selectedMeta.textContent = `Текущий остаток: ${formatNumber(stock)} ${unit}`.trim();
        }
        if (selectedBox) selectedBox.hidden = false;

        if (priceInput) {
            priceInput.value = previousPrice > 0 ? String(previousPrice) : "";
            priceInput.setCustomValidity("");
        }
        if (quantityInput) quantityInput.setCustomValidity("");
        if (previousPriceHint) {
            previousPriceHint.textContent = previousPrice > 0
                ? `Подставлена последняя закупочная цена: ${formatMoney(previousPrice)}`
                : "У товара ещё нет закупочной цены";
        }

        closeDropdown();
        updateSummary();
        updateRetailHint();
        setTimeout(() => quantityInput?.focus(), 50);
    }

    function createProductOption(item) {
        const option = document.createElement("button");
        option.type = "button";
        option.className = "product-option";
        option.dataset.id = item.id ?? "";
        option.dataset.name = item.name || "";
        option.dataset.barcode = item.barcode || "";
        option.dataset.gtin = item.gtin || "";
        option.dataset.ntin = item.ntin || "";
        option.dataset.unit = item.unit || "";
        option.dataset.stock = item.stock ?? 0;
        option.dataset.image = window.NIKA_SHOW_CATALOG_IMAGES === false
            ? ""
            : item.item_image || item.image || "";
        option.dataset.price = item.purchase_price ?? 0;
        option.dataset.lastPrice = item.last_purchase_price ?? item.purchase_price ?? 0;
        option.dataset.retail = item.retail_price ?? 0;
        option.dataset.markup = item.category_markup ?? 0;

        const avatar = document.createElement("span");
        avatar.className = "product-option-avatar";
        if (window.NIKA_SHOW_CATALOG_IMAGES === false) { avatar.hidden = true; } else if (item.item_image || item.image) { const img = document.createElement("img"); img.src = item.item_image || item.image; img.alt = ""; img.loading = "lazy"; avatar.appendChild(img); } else { avatar.textContent = (item.name || "Т").slice(0, 1).toUpperCase(); }

        const main = document.createElement("span");
        main.className = "product-option-main";
        const name = document.createElement("strong");
        name.textContent = item.name || "Без названия";
        const code = document.createElement("small");
        const productCode = item.barcode || item.gtin || item.ntin;
        code.textContent = productCode ? `Код: ${productCode}` : "Без штрихкода";
        main.append(name, code);

        const stock = document.createElement("span");
        stock.className = "product-option-stock";
        stock.textContent = `${formatNumber(item.stock)} ${item.unit || ""}`.trim();

        option.append(avatar, main, stock);
        return option;
    }

    function renderProducts(items, total) {
        if (!dropdown) return;
        dropdown.replaceChildren();

        items.forEach(item => dropdown.appendChild(createProductOption(item)));

        if (total > items.length) {
            const hint = document.createElement("div");
            hint.className = "product-empty";
            const strong = document.createElement("strong");
            strong.textContent = `Показано ${items.length} из ${total}`;
            const span = document.createElement("span");
            span.textContent = "Уточните название или код товара";
            hint.append(strong, span);
            dropdown.appendChild(hint);
        }

        highlightedIndex = -1;
        openDropdown();
    }

    function findExactOption(query) {
        const normalized = query.trim().toLowerCase();
        return getOptions().find(option => {
            return [option.dataset.barcode, option.dataset.gtin, option.dataset.ntin]
                .some(value => (value || "").trim().toLowerCase() === normalized);
        });
    }

    async function loadProducts(query, {selectExact = false, selectFirst = false} = {}) {
        const normalized = query.trim();
        if (normalized.length < 2) {
            showMessage("Введите ещё один символ", "Поиск начнётся после 2 символов");
            return [];
        }

        searchController?.abort();
        searchController = new AbortController();
        showMessage("Поиск товара…", "Пожалуйста, подождите");

        const params = new URLSearchParams({
            q: normalized,
            limit: String(SEARCH_LIMIT),
            offset: "0",
            sort: "name"
        });

        try {
            const response = await fetch(`/api/stock?${params.toString()}`, {
                signal: searchController.signal,
                headers: {"Accept": "application/json"}
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const data = await response.json();
            const items = Array.isArray(data.items) ? data.items : [];
            const total = Number(data.total) || items.length;

            if (!items.length) {
                showMessage("Товар не найден", "Проверьте название или код");
                return [];
            }

            renderProducts(items, total);
            const exact = findExactOption(normalized);
            if (selectExact && exact) {
                selectProduct(exact);
            } else if (selectFirst && getOptions()[0]) {
                selectProduct(getOptions()[0]);
            }
            return items;
        } catch (error) {
            if (error.name !== "AbortError") {
                console.error("Не удалось найти товар:", error);
                showMessage("Не удалось выполнить поиск", "Попробуйте ещё раз");
            }
            return [];
        }
    }

    function scheduleSearch() {
        clearTimeout(searchTimer);
        clearProduct({clearSearch: false});
        const query = searchInput?.value.trim() || "";

        if (query.length < 2) {
            searchController?.abort();
            showMessage(
                query.length ? "Введите ещё один символ" : "Начните вводить название",
                query.length ? "Поиск начнётся после 2 символов" : "Введите не менее 2 символов или отсканируйте штрихкод"
            );
            return;
        }

        searchTimer = setTimeout(() => loadProducts(query, {selectExact: true}), SEARCH_DELAY);
    }

    function highlightOption(index) {
        const options = getOptions();
        if (!options.length) return;

        highlightedIndex = Math.max(0, Math.min(index, options.length - 1));
        options.forEach(option => option.classList.remove("is-highlighted"));
        options[highlightedIndex].classList.add("is-highlighted");
        options[highlightedIndex].scrollIntoView({block: "nearest"});
    }

    searchInput?.addEventListener("focus", function () {
        openDropdown();
        if (this.value.trim().length >= 2 && !getOptions().length) {
            loadProducts(this.value.trim(), {selectExact: true});
        }
    });
    searchInput?.addEventListener("click", openDropdown);
    searchInput?.addEventListener("input", scheduleSearch);

    searchInput?.addEventListener("keydown", async function (event) {
        const options = getOptions();

        if (event.key === "Escape") {
            closeDropdown();
            return;
        }
        if (event.key === "ArrowDown") {
            event.preventDefault();
            highlightOption(highlightedIndex + 1);
            return;
        }
        if (event.key === "ArrowUp") {
            event.preventDefault();
            highlightOption(highlightedIndex <= 0 ? options.length - 1 : highlightedIndex - 1);
            return;
        }
        if (event.key !== "Enter") return;

        event.preventDefault();
        clearTimeout(searchTimer);

        if (highlightedIndex >= 0 && options[highlightedIndex]) {
            selectProduct(options[highlightedIndex]);
            return;
        }

        const query = searchInput.value.trim();
        const exact = findExactOption(query);
        if (exact) {
            selectProduct(exact);
            return;
        }

        await loadProducts(query, {selectExact: true, selectFirst: true});
    });

    dropdown?.addEventListener("click", function (event) {
        const option = event.target.closest(".product-option");
        if (option) selectProduct(option);
    });

    document.addEventListener("click", function (event) {
        if (!event.target.closest(".product-picker")) closeDropdown();
    });

    clearSelected?.addEventListener("click", () => {
        clearProduct();
        showMessage("Начните вводить название", "Введите не менее 2 символов или отсканируйте штрихкод");
        searchInput?.focus();
    });

    document.querySelectorAll(".number-step").forEach(button => {
        button.addEventListener("click", () => {
            const target = document.getElementById(button.dataset.target);
            if (!target) return;
            const next = Math.max(0.001, Number(target.value || 0) + Number(button.dataset.step || 0));
            target.value = Number(next.toFixed(3));
            target.setCustomValidity("");
            updateSummary();
        });
    });

    document.querySelectorAll(".quick-values button").forEach(button => {
        button.addEventListener("click", () => {
            if (quantityInput) {
                quantityInput.value = button.dataset.value || "";
                quantityInput.setCustomValidity("");
            }
            updateSummary();
        });
    });

    quantityInput?.addEventListener("input", () => {
        quantityInput.setCustomValidity("");
        updateSummary();
    });
    priceInput?.addEventListener("input", () => {
        priceInput.setCustomValidity("");
        updateSummary();
        updateRetailHint();
    });
    updateRetailInput?.addEventListener("change", updateRetailHint);

    document.getElementById("incomeReset")?.addEventListener("click", () => {
        form?.reset();
        quantityInput?.setCustomValidity("");
        priceInput?.setCustomValidity("");
        clearProduct();
        updateSummary();
        showMessage("Начните вводить название", "Введите не менее 2 символов или отсканируйте штрихкод");
        searchInput?.focus();
    });

    form?.addEventListener("submit", function (event) {
        if (!itemIdInput?.value) {
            event.preventDefault();
            searchInput?.setCustomValidity("Выберите товар из списка");
            searchInput?.reportValidity();
            openDropdown();
            return;
        }

        const quantity = Number(quantityInput?.value || 0);
        const price = Number(priceInput?.value || 0);

        quantityInput?.setCustomValidity("");
        priceInput?.setCustomValidity("");

        if (quantity <= 0) {
            event.preventDefault();
            quantityInput?.setCustomValidity("Количество должно быть больше нуля");
            quantityInput?.reportValidity();
            return;
        }

        if (price < 0) {
            event.preventDefault();
            priceInput?.setCustomValidity("Цена не может быть отрицательной");
            priceInput?.reportValidity();
            return;
        }
    });

    const historySearch = document.getElementById("incomeHistorySearch");
    const historyEmpty = document.getElementById("incomeHistoryEmpty");

    function filterHistory() {
        const query = (historySearch?.value || "").trim().toLowerCase();
        const records = document.querySelectorAll(".income-history-record");
        let visibleCount = 0;

        records.forEach(record => {
            const visible = !query || (record.dataset.search || "").includes(query);
            record.style.display = visible ? "" : "none";
            if (visible) visibleCount += 1;
        });

        if (historyEmpty) historyEmpty.hidden = visibleCount !== 0;
    }

    historySearch?.addEventListener("input", filterHistory);
    updateSummary();
});