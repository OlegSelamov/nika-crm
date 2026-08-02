document.addEventListener("DOMContentLoaded", function () {
    const SEARCH_DELAY = 300;
    const SEARCH_LIMIT = 30;

    const form = document.getElementById("writeoffForm");
    const searchInput = document.getElementById("writeoffProductSearch");
    const itemIdInput = document.getElementById("writeoffItemId");
    const dropdown = document.getElementById("writeoffProductList");

    const selectedBox = document.getElementById("selectedWriteoffProduct");
    const selectedAvatar = document.getElementById("selectedWriteoffAvatar");
    const selectedName = document.getElementById("selectedWriteoffName");
    const selectedMeta = document.getElementById("selectedWriteoffMeta");
    const selectedStatus = document.getElementById("selectedWriteoffStatus");

    const quantityInput = document.getElementById("writeoffQuantity");
    const quantityHint = document.getElementById("writeoffQuantityHint");
    const reasonSelect = document.getElementById("writeoffReason");
    const commentInput = document.getElementById("writeoffComment");

    const currentStockNode = document.getElementById("writeoffCurrentStock");
    const summaryQuantityNode = document.getElementById("writeoffSummaryQuantity");
    const remainingStockNode = document.getElementById("writeoffRemainingStock");
    const summaryResult = document.querySelector(".writeoff-summary-result");
    const warning = document.getElementById("writeoffWarning");
    const submitButton = document.querySelector(".writeoff-submit");

    let currentStock = 0;
    let currentUnit = "";
    let highlightedIndex = -1;
    let searchTimer = null;
    let searchController = null;

    function formatNumber(value) {
        return new Intl.NumberFormat("ru-RU", {
            maximumFractionDigits: 3
        }).format(Number(value || 0));
    }

    function openDropdown() {
        dropdown?.classList.add("open");
    }

    function closeDropdown() {
        dropdown?.classList.remove("open");
        highlightedIndex = -1;
        getOptions().forEach(option => option.classList.remove("is-highlighted"));
    }

    function getOptions() {
        return Array.from(dropdown?.querySelectorAll(".product-option") || []);
    }

    function updateSummary() {
        const quantity = Number(quantityInput?.value || 0);
        const remaining = currentStock - quantity;
        const isInvalid = quantity > currentStock || quantity <= 0 || currentStock <= 0;

        currentStockNode.textContent = `${formatNumber(currentStock)} ${currentUnit}`.trim();
        summaryQuantityNode.textContent = `${formatNumber(quantity)} ${currentUnit}`.trim();
        remainingStockNode.textContent = `${formatNumber(remaining)} ${currentUnit}`.trim();

        summaryResult?.classList.toggle("is-ok", remaining >= 0);
        warning.hidden = !(quantity > currentStock);
        submitButton.disabled = !itemIdInput.value || isInvalid;

        if (quantityInput && itemIdInput.value) {
            quantityInput.max = currentStock;
        }
    }

    function clearProduct({clearSearch = true} = {}) {
        itemIdInput.value = "";
        if (clearSearch) searchInput.value = "";
        searchInput.setCustomValidity("");
        selectedBox.hidden = true;
        currentStock = 0;
        currentUnit = "";
        quantityInput.value = "";
        quantityHint.textContent = "Сначала выберите товар";
        updateSummary();
    }

    function selectProduct(option) {
        const name = option.dataset.name || "";
        currentStock = Number(option.dataset.stock || 0);
        currentUnit = option.dataset.unit || "";

        itemIdInput.value = option.dataset.id || "";
        searchInput.value = name;
        searchInput.setCustomValidity("");

        selectedAvatar.textContent = (name || "Т").slice(0, 1).toUpperCase();
        selectedName.textContent = name;
        selectedMeta.textContent = `Доступно: ${formatNumber(currentStock)} ${currentUnit}`.trim();

        selectedStatus.className = "selected-product-status";

        if (currentStock <= 0) {
            selectedStatus.textContent = "Нет в наличии";
            selectedStatus.classList.add("is-empty");
        } else if (currentStock <= 5) {
            selectedStatus.textContent = "Мало";
            selectedStatus.classList.add("is-low");
        } else {
            selectedStatus.textContent = "В наличии";
        }

        selectedBox.hidden = false;
        quantityInput.value = "";
        quantityHint.textContent = `Максимум для списания: ${formatNumber(currentStock)} ${currentUnit}`.trim();

        closeDropdown();
        updateSummary();

        if (currentStock > 0) {
            setTimeout(() => quantityInput.focus(), 50);
        }
    }

    function showMessage(title, text) {
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

        const avatar = document.createElement("span");
        avatar.className = "product-option-avatar";
        avatar.textContent = (item.name || "Т").slice(0, 1).toUpperCase();

        const main = document.createElement("span");
        main.className = "product-option-main";
        const name = document.createElement("strong");
        name.textContent = item.name || "Без названия";
        const code = document.createElement("small");
        const productCode = item.barcode || item.gtin || item.ntin;
        code.textContent = productCode ? `Код: ${productCode}` : "Без штрихкода";
        main.append(name, code);

        const stock = document.createElement("span");
        const stockValue = Number(item.stock || 0);
        stock.className = "product-option-stock";
        stock.classList.add(stockValue <= 0 ? "is-empty" : stockValue <= 5 ? "is-low" : "is-ok");
        stock.textContent = `${formatNumber(stockValue)} ${item.unit || ""}`.trim();

        option.append(avatar, main, stock);
        option.addEventListener("click", () => selectProduct(option));
        return option;
    }

    function renderProducts(items, total) {
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
        return getOptions().find(option =>
            [option.dataset.barcode, option.dataset.gtin, option.dataset.ntin]
                .some(value => (value || "").trim().toLowerCase() === normalized)
        );
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

        const params = new URLSearchParams({q: normalized, limit: String(SEARCH_LIMIT), offset: "0", sort: "name"});

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
            if (selectExact && exact) selectProduct(exact);
            else if (selectFirst && getOptions()[0]) selectProduct(getOptions()[0]);
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
        const query = searchInput.value.trim();

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

    searchInput.addEventListener("focus", function () {
        if (itemIdInput.value) return;
        const query = searchInput.value.trim();
        if (query.length >= 2) scheduleSearch();
        else showMessage("Начните вводить название", "Введите не менее 2 символов или отсканируйте штрихкод");
    });
    searchInput.addEventListener("input", scheduleSearch);

    searchInput.addEventListener("keydown", function (event) {
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

        if (highlightedIndex >= 0 && options[highlightedIndex]) {
            selectProduct(options[highlightedIndex]);
            return;
        }

        clearTimeout(searchTimer);
        loadProducts(searchInput.value, {selectExact: true, selectFirst: true});
    });

    document.addEventListener("click", function (event) {
        if (!event.target.closest(".product-picker")) {
            closeDropdown();
        }
    });

    document.getElementById("clearWriteoffProduct").addEventListener("click", () => {
        clearProduct();
        searchInput.focus();
    });

    document.querySelectorAll(".number-step").forEach(button => {
        button.addEventListener("click", () => {
            if (!itemIdInput.value || currentStock <= 0) return;

            const step = Number(button.dataset.step || 0);
            const current = Number(quantityInput.value || 0);
            const next = Math.min(currentStock, Math.max(0.001, current + step));

            quantityInput.value = Number(next.toFixed(3));
            updateSummary();
        });
    });

    document.querySelectorAll(".quick-values button[data-value]").forEach(button => {
        button.addEventListener("click", () => {
            if (!itemIdInput.value || currentStock <= 0) return;

            quantityInput.value = Math.min(
                Number(button.dataset.value || 0),
                currentStock
            );

            updateSummary();
        });
    });

    document.getElementById("writeoffAllStock").addEventListener("click", () => {
        if (!itemIdInput.value || currentStock <= 0) return;

        quantityInput.value = currentStock;
        updateSummary();
    });

    quantityInput.addEventListener("input", updateSummary);

    reasonSelect.addEventListener("change", function () {
        if (!this.value) return;

        if (!commentInput.value.trim() || commentInput.dataset.autoReason === "1") {
            commentInput.value = this.value;
            commentInput.dataset.autoReason = "1";
        }

        commentInput.setCustomValidity("");
    });

    commentInput.addEventListener("input", function () {
        this.dataset.autoReason = "0";
        this.setCustomValidity("");
    });

    document.getElementById("writeoffReset").addEventListener("click", () => {
        form.reset();
        clearProduct();
        reasonSelect.value = "";
        commentInput.dataset.autoReason = "0";
        searchInput.focus();
    });

    form.addEventListener("submit", function (event) {
        const quantity = Number(quantityInput.value || 0);

        if (!itemIdInput.value) {
            event.preventDefault();
            searchInput.setCustomValidity("Выберите товар из списка");
            searchInput.reportValidity();
            openDropdown();
            return;
        }

        if (currentStock <= 0) {
            event.preventDefault();
            searchInput.setCustomValidity("У выбранного товара нет доступного остатка");
            searchInput.reportValidity();
            return;
        }

        if (quantity <= 0) {
            event.preventDefault();
            quantityInput.setCustomValidity("Количество должно быть больше нуля");
            quantityInput.reportValidity();
            return;
        }

        if (quantity > currentStock) {
            event.preventDefault();
            quantityInput.setCustomValidity("Нельзя списать больше текущего остатка");
            quantityInput.reportValidity();
            warning.hidden = false;
            return;
        }

        quantityInput.setCustomValidity("");

        if (!commentInput.value.trim()) {
            event.preventDefault();
            commentInput.setCustomValidity("Укажите причину списания");
            commentInput.reportValidity();
            return;
        }

        commentInput.setCustomValidity("");
    });

    updateSummary();
});
