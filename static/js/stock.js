let activeStockFilter = "all";

function getStockRecords() {
    const desktopVisible = window.innerWidth > 768;
    const selector = desktopVisible
        ? "#stockTableBody .stock-record"
        : "#stockMobileList .stock-record";

    return Array.from(document.querySelectorAll(selector));
}

function applyStockFilters() {
    const query = (document.getElementById("stockSearch")?.value || "").trim().toLowerCase();
    const category = (document.getElementById("stockCategory")?.value || "").toLowerCase();
    const records = document.querySelectorAll(".stock-record");
    const visibleKeys = new Set();

    records.forEach(record => {
        const searchText = [
            record.dataset.name || "",
            record.dataset.category || "",
            record.dataset.unit || ""
        ].join(" ");

        const matchesSearch = !query || searchText.includes(query);
        const matchesCategory = !category || record.dataset.category === category;
        const matchesStatus = activeStockFilter === "all" || record.dataset.status === activeStockFilter;
        const visible = matchesSearch && matchesCategory && matchesStatus;

        record.style.display = visible ? "" : "none";

        if (visible) {
            const key = [
                record.dataset.name,
                record.dataset.category,
                record.dataset.stock,
                record.dataset.retail
            ].join("|");
            visibleKeys.add(key);
        }
    });

    const count = visibleKeys.size;
    const countNode = document.getElementById("stockVisibleCount");
    const emptyNode = document.getElementById("stockSearchEmpty");

    if (countNode) countNode.textContent = count;
    if (emptyNode) emptyNode.hidden = count !== 0;
}

function sortStockRecords() {
    const sortValue = document.getElementById("stockSort")?.value || "name";
    const containers = [
        document.getElementById("stockTableBody"),
        document.getElementById("stockMobileList")
    ].filter(Boolean);

    containers.forEach(container => {
        const records = Array.from(container.querySelectorAll(".stock-record"));

        records.sort((a, b) => {
            if (sortValue === "stock-asc") {
                return Number(a.dataset.stock || 0) - Number(b.dataset.stock || 0);
            }

            if (sortValue === "stock-desc") {
                return Number(b.dataset.stock || 0) - Number(a.dataset.stock || 0);
            }

            if (sortValue === "retail-desc") {
                return Number(b.dataset.retail || 0) - Number(a.dataset.retail || 0);
            }

            if (sortValue === "retail-asc") {
                return Number(a.dataset.retail || 0) - Number(b.dataset.retail || 0);
            }

            return (a.dataset.name || "").localeCompare(
                b.dataset.name || "",
                "ru",
                {sensitivity: "base"}
            );
        });

        records.forEach(record => container.appendChild(record));
    });

    applyStockFilters();
}

document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".stock-tab").forEach(button => {
        button.addEventListener("click", () => {
            activeStockFilter = button.dataset.filter || "all";

            document.querySelectorAll(".stock-tab").forEach(tab => {
                tab.classList.toggle("is-active", tab === button);
            });

            applyStockFilters();
        });
    });

    document.getElementById("stockSearch")?.addEventListener("input", applyStockFilters);
    document.getElementById("stockCategory")?.addEventListener("change", applyStockFilters);
    document.getElementById("stockSort")?.addEventListener("change", sortStockRecords);

    window.addEventListener("resize", applyStockFilters);

    sortStockRecords();
});