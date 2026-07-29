document.addEventListener("DOMContentLoaded", function () {
    const searchInput = document.getElementById("incomeProductSearch");
    const itemIdInput = document.getElementById("incomeItemId");
    const dropdown = document.getElementById("incomeProductList");
    const options = Array.from(document.querySelectorAll(".product-option"));
    const noProducts = document.getElementById("incomeNoProducts");
    const form = document.getElementById("incomeForm");

    const selectedBox = document.getElementById("selectedProduct");
    const selectedAvatar = document.getElementById("selectedProductAvatar");
    const selectedName = document.getElementById("selectedProductName");
    const selectedMeta = document.getElementById("selectedProductMeta");
    const clearSelected = document.getElementById("clearSelectedProduct");

    const quantityInput = document.getElementById("incomeQuantity");
    const priceInput = document.getElementById("incomePrice");
    const previousPriceHint = document.getElementById("previousPriceHint");

    const summaryQuantity = document.getElementById("summaryQuantity");
    const summaryPrice = document.getElementById("summaryPrice");
    const summaryTotal = document.getElementById("summaryTotal");

    let highlightedIndex = -1;

    function formatNumber(value, maximumFractionDigits = 3) {
        return new Intl.NumberFormat("ru-RU", {
            maximumFractionDigits
        }).format(Number(value || 0));
    }

    function formatMoney(value) {
        return new Intl.NumberFormat("ru-RU", {
            maximumFractionDigits: 2
        }).format(Number(value || 0)) + " ₸";
    }

    function updateSummary() {
        const quantity = Number(quantityInput?.value || 0);
        const price = Number(priceInput?.value || 0);

        if (summaryQuantity) summaryQuantity.textContent = formatNumber(quantity);
        if (summaryPrice) summaryPrice.textContent = formatMoney(price);
        if (summaryTotal) summaryTotal.textContent = formatMoney(quantity * price);
    }

    function openDropdown() {
        dropdown?.classList.add("open");
    }

    function closeDropdown() {
        dropdown?.classList.remove("open");
        highlightedIndex = -1;
        options.forEach(option => option.classList.remove("is-highlighted"));
    }

    function clearProduct() {
        if (itemIdInput) itemIdInput.value = "";
        if (searchInput) {
            searchInput.value = "";
            searchInput.setCustomValidity("");
        }

        if (selectedBox) selectedBox.hidden = true;
        if (previousPriceHint) {
            previousPriceHint.textContent = "После выбора товара подставится последняя закупочная цена";
        }
    }

    function selectProduct(option) {
        if (!option) return;

        const name = option.dataset.name || "";
        const unit = option.dataset.unit || "";
        const stock = option.dataset.stock || "0";
        const previousPrice = Number(option.dataset.price || 0);

        itemIdInput.value = option.dataset.id || "";
        searchInput.value = name;
        searchInput.setCustomValidity("");

        if (selectedAvatar) selectedAvatar.textContent = (name || "Т").slice(0, 1).toUpperCase();
        if (selectedName) selectedName.textContent = name;
        if (selectedMeta) {
            selectedMeta.textContent = `Текущий остаток: ${formatNumber(stock)} ${unit}`.trim();
        }

        if (selectedBox) selectedBox.hidden = false;

        if (previousPrice > 0) {
            priceInput.value = previousPrice;
            if (previousPriceHint) {
                previousPriceHint.textContent = `Подставлена предыдущая закупочная цена: ${formatMoney(previousPrice)}`;
            }
        }

        closeDropdown();
        updateSummary();

        setTimeout(() => quantityInput?.focus(), 50);
    }

    function getVisibleOptions() {
        return options.filter(option => option.style.display !== "none");
    }

    function highlightOption(index) {
        const visible = getVisibleOptions();
        if (!visible.length) return;

        highlightedIndex = Math.max(0, Math.min(index, visible.length - 1));

        options.forEach(option => option.classList.remove("is-highlighted"));
        visible[highlightedIndex].classList.add("is-highlighted");
        visible[highlightedIndex].scrollIntoView({block:"nearest"});
    }

    function filterProducts() {
        const query = searchInput.value.trim().toLowerCase();
        let visibleCount = 0;
        let exactCodeOption = null;
        let exactNameOption = null;

        itemIdInput.value = "";
        if (selectedBox) selectedBox.hidden = true;

        options.forEach(function (option) {
            const haystack = (option.dataset.search || "").toLowerCase();
            const name = (option.dataset.nameSearch || "").trim();
            const barcode = (option.dataset.barcode || "").trim().toLowerCase();
            const gtin = (option.dataset.gtin || "").trim().toLowerCase();
            const ntin = (option.dataset.ntin || "").trim().toLowerCase();

            const visible = !query || haystack.includes(query);
            option.style.display = visible ? "grid" : "none";

            if (visible) visibleCount++;

            if (query && (query === barcode || query === gtin || query === ntin)) {
                exactCodeOption = option;
            }

            if (query && query === name) {
                exactNameOption = option;
            }
        });

        if (noProducts) {
            noProducts.style.display = visibleCount === 0 ? "block" : "none";
        }

        highlightedIndex = -1;
        openDropdown();

        if (exactCodeOption) {
            selectProduct(exactCodeOption);
            return exactCodeOption;
        }

        if (exactNameOption && visibleCount === 1) {
            selectProduct(exactNameOption);
            return exactNameOption;
        }

        return null;
    }

    searchInput?.addEventListener("focus", filterProducts);
    searchInput?.addEventListener("click", filterProducts);
    searchInput?.addEventListener("input", filterProducts);

    searchInput?.addEventListener("keydown", function (event) {
        const visible = getVisibleOptions();

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
            highlightOption(highlightedIndex <= 0 ? visible.length - 1 : highlightedIndex - 1);
            return;
        }

        if (event.key !== "Enter") return;

        event.preventDefault();

        if (highlightedIndex >= 0 && visible[highlightedIndex]) {
            selectProduct(visible[highlightedIndex]);
            return;
        }

        const exactOption = filterProducts();

        if (exactOption) {
            selectProduct(exactOption);
            return;
        }

        if (visible[0]) {
            selectProduct(visible[0]);
        }
    });

    options.forEach(option => {
        option.addEventListener("click", () => selectProduct(option));
    });

    document.addEventListener("click", function (event) {
        if (!event.target.closest(".product-picker")) {
            closeDropdown();
        }
    });

    clearSelected?.addEventListener("click", () => {
        clearProduct();
        searchInput?.focus();
        filterProducts();
    });

    document.querySelectorAll(".number-step").forEach(button => {
        button.addEventListener("click", () => {
            const target = document.getElementById(button.dataset.target);
            if (!target) return;

            const step = Number(button.dataset.step || 0);
            const current = Number(target.value || 0);
            const next = Math.max(0.001, current + step);

            target.value = Number(next.toFixed(3));
            updateSummary();
        });
    });

    document.querySelectorAll(".quick-values button").forEach(button => {
        button.addEventListener("click", () => {
            quantityInput.value = button.dataset.value || "";
            updateSummary();
        });
    });

    quantityInput?.addEventListener("input", updateSummary);
    priceInput?.addEventListener("input", updateSummary);

    document.getElementById("incomeReset")?.addEventListener("click", () => {
        form?.reset();
        clearProduct();
        updateSummary();
        searchInput?.focus();
    });

    form?.addEventListener("submit", function (event) {
        if (!itemIdInput.value) {
            event.preventDefault();
            searchInput.setCustomValidity("Выберите товар из списка");
            searchInput.reportValidity();
            openDropdown();
            return;
        }

        const quantity = Number(quantityInput?.value || 0);
        const price = Number(priceInput?.value || 0);

        if (quantity <= 0) {
            event.preventDefault();
            quantityInput.setCustomValidity("Количество должно быть больше нуля");
            quantityInput.reportValidity();
            return;
        }

        quantityInput.setCustomValidity("");

        if (price < 0) {
            event.preventDefault();
            priceInput.setCustomValidity("Цена не может быть отрицательной");
            priceInput.reportValidity();
            return;
        }

        priceInput.setCustomValidity("");
    });

    const historySearch = document.getElementById("incomeHistorySearch");
    const historyEmpty = document.getElementById("incomeHistoryEmpty");

    function filterHistory() {
        const query = (historySearch?.value || "").trim().toLowerCase();
        const records = document.querySelectorAll(".income-history-record");
        const visibleKeys = new Set();

        records.forEach(record => {
            const visible = !query || (record.dataset.search || "").includes(query);
            record.style.display = visible ? "" : "none";

            if (visible) {
                visibleKeys.add(record.dataset.search + "|" + record.textContent.trim());
            }
        });

        if (historyEmpty) {
            historyEmpty.hidden = visibleKeys.size !== 0;
        }
    }

    historySearch?.addEventListener("input", filterHistory);

    updateSummary();
});