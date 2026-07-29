document.addEventListener("DOMContentLoaded", function () {
    const form = document.getElementById("writeoffForm");
    const searchInput = document.getElementById("writeoffProductSearch");
    const itemIdInput = document.getElementById("writeoffItemId");
    const dropdown = document.getElementById("writeoffProductList");
    const options = Array.from(document.querySelectorAll(".product-option"));
    const noProducts = document.getElementById("writeoffNoProducts");

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
        options.forEach(option => option.classList.remove("is-highlighted"));
    }

    function getVisibleOptions() {
        return options.filter(option => option.style.display !== "none");
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

    function clearProduct() {
        itemIdInput.value = "";
        searchInput.value = "";
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

    function filterProducts() {
        const query = searchInput.value.trim().toLowerCase();
        let visibleCount = 0;
        let exactCodeOption = null;
        let exactNameOption = null;

        itemIdInput.value = "";
        selectedBox.hidden = true;

        options.forEach(option => {
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

        noProducts.style.display = visibleCount === 0 ? "block" : "none";
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

    function highlightOption(index) {
        const visible = getVisibleOptions();
        if (!visible.length) return;

        highlightedIndex = Math.max(0, Math.min(index, visible.length - 1));

        options.forEach(option => option.classList.remove("is-highlighted"));
        visible[highlightedIndex].classList.add("is-highlighted");
        visible[highlightedIndex].scrollIntoView({block:"nearest"});
    }

    searchInput.addEventListener("focus", filterProducts);
    searchInput.addEventListener("click", filterProducts);
    searchInput.addEventListener("input", filterProducts);

    searchInput.addEventListener("keydown", function (event) {
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

        const exact = filterProducts();

        if (exact) {
            selectProduct(exact);
        } else if (visible[0]) {
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

    document.getElementById("clearWriteoffProduct").addEventListener("click", () => {
        clearProduct();
        searchInput.focus();
        filterProducts();
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