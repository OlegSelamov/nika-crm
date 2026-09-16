const STOCK_PAGE_SIZE = 50;
let activeStockFilter = "all";
let stockOffset = document.querySelectorAll("#stockTableBody .stock-record").length;
let stockTotal = Number((document.getElementById("stockResultTotal")?.textContent || "").replace(/\D/g, "")) || stockOffset;
let stockSearchTimer = null;
let stockRequestController = null;

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function formatMoney(value) {
    return new Intl.NumberFormat("ru-RU", {maximumFractionDigits: 0}).format(Number(value) || 0);
}

function formatQuantity(value) {
    return new Intl.NumberFormat("ru-RU", {maximumFractionDigits: 3}).format(Number(value) || 0);
}

function stockStatus(stock) {
    const value = Number(stock) || 0;
    if (value < 0) return {key: "out", text: "Требует проверки"};
    if (value === 0) return {key: "out", text: "Нет в наличии"};
    if (value <= 5) return {key: "low", text: "Заканчивается"};
    return {key: "normal", text: "В наличии"};
}

function buildDesktopRow(item) {
    const stock = Number(item.stock) || 0;
    const purchase = Number(item.purchase_price) || 0;
    const retail = Number(item.retail_price) || 0;
    const status = stockStatus(stock);
    const name = escapeHtml(item.name || "Без названия");
    const category = escapeHtml(item.category || "Без категории");
    const unit = escapeHtml(item.unit || "—");
    const initial = escapeHtml((item.name || "Т").trim().charAt(0).toUpperCase() || "Т");
    const image = escapeHtml(item.item_image || item.image || "");
    const visual = window.NIKA_SHOW_CATALOG_IMAGES === false
        ? ""
        : image
            ? `<img class="stock-product-image" src="${image}" alt="" loading="lazy">`
            : `<div class="stock-product-icon">${initial}</div>`;

    return `
        <tr class="stock-record">
            <td>
                <div class="stock-product">
                    ${visual}
                    <div><strong>${name}</strong><small>${status.text}</small></div>
                </div>
            </td>
            <td><span class="stock-category-badge">${category}</span></td>
            <td>${unit}</td>
            <td>
                <div class="stock-balance">
                    <strong class="stock-balance-value stock-balance-value--${status.key}">${formatQuantity(stock)}</strong>
                    <span class="stock-status stock-status--${status.key}">${status.text}</span>
                </div>
            </td>
            <td>${formatMoney(purchase)} ₸</td>
            <td><strong class="stock-price">${formatMoney(retail)} ₸</strong></td>
            <td>${formatMoney(stock * purchase)} ₸</td>
        </tr>`;
}

function buildMobileCard(item) {
    const stock = Number(item.stock) || 0;
    const purchase = Number(item.purchase_price) || 0;
    const retail = Number(item.retail_price) || 0;
    const status = stockStatus(stock);
    const name = escapeHtml(item.name || "Без названия");
    const category = escapeHtml(item.category || "Без категории");
    const unit = escapeHtml(item.unit || "");
    const initial = escapeHtml((item.name || "Т").trim().charAt(0).toUpperCase() || "Т");
    const image = escapeHtml(item.item_image || item.image || "");
    const visual = window.NIKA_SHOW_CATALOG_IMAGES === false
        ? ""
        : image
            ? `<img class="stock-product-image" src="${image}" alt="" loading="lazy">`
            : `<div class="stock-product-icon">${initial}</div>`;

    return `
        <article class="stock-mobile-card stock-record">
            <div class="stock-mobile-top">
                <div class="stock-product">
                    ${visual}
                    <div><strong>${name}</strong><small>${category}</small></div>
                </div>
                <span class="stock-status stock-status--${status.key}">${status.text}</span>
            </div>
            <div class="stock-mobile-grid">
                <div><span>Остаток</span><strong class="stock-balance-value stock-balance-value--${status.key}">${formatQuantity(stock)} ${unit}</strong></div>
                <div><span>Закуп</span><strong>${formatMoney(purchase)} ₸</strong></div>
                <div><span>Розница</span><strong>${formatMoney(retail)} ₸</strong></div>
                <div><span>Стоимость остатка</span><strong>${formatMoney(stock * purchase)} ₸</strong></div>
            </div>
        </article>`;
}

function updateStockState(loadedCount, total, hasMore) {
    stockOffset = loadedCount;
    stockTotal = total;

    const countNode = document.getElementById("stockVisibleCount");
    const totalNode = document.getElementById("stockResultTotal");
    const emptyNode = document.getElementById("stockSearchEmpty");
    const moreWrap = document.getElementById("stockLoadMoreWrap");

    if (countNode) countNode.textContent = String(loadedCount);
    if (totalNode) totalNode.textContent = `из ${total}`;
    if (emptyNode) emptyNode.hidden = total !== 0;
    if (moreWrap) moreWrap.hidden = !hasMore;
}

async function fetchAllNegativeStock({query = "", category = ""} = {}) {
    const negativeItems = [];
    let offset = 0;

    while (true) {
        const params = new URLSearchParams({
            q: query,
            category,
            status: "out",
            sort: "stock-asc",
            offset: String(offset),
            limit: "100"
        });
        const response = await fetch(`/api/stock?${params.toString()}`, {
            headers: {"Accept": "application/json"}
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();
        const items = Array.isArray(data.items) ? data.items : [];
        let reachedZero = false;

        for (const item of items) {
            if (Number(item.stock || 0) < 0) negativeItems.push(item);
            else {
                reachedZero = true;
                break;
            }
        }

        if (reachedZero || !items.length || !data.has_more) break;
        offset += items.length;
    }

    return negativeItems;
}

async function refreshNegativeStockCount() {
    const counter = document.getElementById("negativeStockCount");
    if (!counter) return;
    try {
        const items = await fetchAllNegativeStock();
        counter.textContent = String(items.length);
        counter.closest(".stock-tab")?.classList.toggle("has-warning", items.length > 0);
    } catch (error) {
        console.error("Не удалось посчитать минусовые остатки:", error);
        counter.textContent = "!";
    }
}

function ensureNegativeStockTab() {
    const tabs = document.querySelector(".stock-tabs");
    if (!tabs || document.getElementById("negativeStockTab")) return;

    const button = document.createElement("button");
    button.id = "negativeStockTab";
    button.className = "stock-tab";
    button.type = "button";
    button.dataset.filter = "negative";
    button.innerHTML = `Требуют проверки <span id="negativeStockCount">…</span>`;
    tabs.appendChild(button);

    const style = document.createElement("style");
    style.textContent = `
        #negativeStockTab.has-warning{border-color:#fecaca;background:#fff5f5;color:#b42318}
        #negativeStockTab.has-warning span{background:#fee2e2;color:#b42318}
    `;
    document.head.appendChild(style);
}

async function loadStock({append = false} = {}) {
    if (stockRequestController) stockRequestController.abort();
    stockRequestController = new AbortController();

    const query = (document.getElementById("stockSearch")?.value || "").trim();
    const category = document.getElementById("stockCategory")?.value || "";
    const sort = document.getElementById("stockSort")?.value || "name";
    const offset = append ? stockOffset : 0;
    const moreButton = document.getElementById("stockLoadMore");

    if (moreButton) {
        moreButton.disabled = true;
        moreButton.textContent = "Загрузка…";
    }

    try {
        let items = [];
        let total = 0;
        let hasMore = false;

        if (activeStockFilter === "negative") {
            items = await fetchAllNegativeStock({query, category});
            total = items.length;
            append = false;
        } else {
            const params = new URLSearchParams({
                q: query,
                category,
                status: activeStockFilter,
                sort,
                offset: String(offset),
                limit: String(STOCK_PAGE_SIZE)
            });

            const response = await fetch(`/api/stock?${params.toString()}`, {
                signal: stockRequestController.signal,
                headers: {"Accept": "application/json"}
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const data = await response.json();
            items = Array.isArray(data.items) ? data.items : [];
            total = Number(data.total) || 0;
            hasMore = Boolean(data.has_more);
        }

        const tableBody = document.getElementById("stockTableBody");
        const mobileList = document.getElementById("stockMobileList");

        if (!append) {
            if (tableBody) tableBody.innerHTML = "";
            if (mobileList) mobileList.innerHTML = "";
        }

        if (tableBody) tableBody.insertAdjacentHTML("beforeend", items.map(buildDesktopRow).join(""));
        if (mobileList) mobileList.insertAdjacentHTML("beforeend", items.map(buildMobileCard).join(""));

        const loadedCount = (append ? stockOffset : 0) + items.length;
        updateStockState(loadedCount, total, hasMore);
    } catch (error) {
        if (error.name !== "AbortError") {
            console.error("Не удалось загрузить остатки:", error);
        }
    } finally {
        if (moreButton) {
            moreButton.disabled = false;
            moreButton.textContent = "Показать ещё";
        }
    }
}

function scheduleStockReload() {
    clearTimeout(stockSearchTimer);
    stockSearchTimer = setTimeout(() => loadStock(), 300);
}

document.addEventListener("DOMContentLoaded", () => {
    ensureNegativeStockTab();

    document.querySelectorAll(".stock-tab").forEach(button => {
        button.addEventListener("click", () => {
            activeStockFilter = button.dataset.filter || "all";
            document.querySelectorAll(".stock-tab").forEach(tab => {
                tab.classList.toggle("is-active", tab === button);
            });
            loadStock();
        });
    });

    document.getElementById("stockSearch")?.addEventListener("input", scheduleStockReload);
    document.getElementById("stockCategory")?.addEventListener("change", () => loadStock());
    document.getElementById("stockSort")?.addEventListener("change", () => loadStock());
    document.getElementById("stockLoadMore")?.addEventListener("click", () => loadStock({append: true}));

    updateStockState(stockOffset, stockTotal, stockOffset < stockTotal);
    refreshNegativeStockCount();
});
