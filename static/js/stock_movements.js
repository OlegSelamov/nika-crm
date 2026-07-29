let activeMovementFilter = "all";

function applyMovementFilters() {
    const query = (document.getElementById("movementSearch")?.value || "").trim().toLowerCase();
    const dateFrom = document.getElementById("movementDateFrom")?.value || "";
    const dateTo = document.getElementById("movementDateTo")?.value || "";
    const records = document.querySelectorAll(".movement-record");
    const visibleKeys = new Set();

    records.forEach(record => {
        const searchText = [
            record.dataset.name || "",
            record.dataset.typeText || ""
        ].join(" ");

        const recordDate = (record.dataset.date || "").slice(0, 10);
        const matchesSearch = !query || searchText.includes(query);
        const matchesType = activeMovementFilter === "all" || record.dataset.type === activeMovementFilter;
        const matchesFrom = !dateFrom || (recordDate && recordDate >= dateFrom);
        const matchesTo = !dateTo || (recordDate && recordDate <= dateTo);
        const visible = matchesSearch && matchesType && matchesFrom && matchesTo;

        record.style.display = visible ? "" : "none";

        if (visible) {
            const key = [
                record.dataset.name,
                record.dataset.type,
                record.dataset.quantity,
                record.dataset.total,
                record.dataset.date
            ].join("|");
            visibleKeys.add(key);
        }
    });

    const count = visibleKeys.size;
    const countNode = document.getElementById("movementsVisibleCount");
    const emptyNode = document.getElementById("movementsSearchEmpty");

    if (countNode) countNode.textContent = count;
    if (emptyNode) emptyNode.hidden = count !== 0;
}

function sortMovementRecords() {
    const sortValue = document.getElementById("movementSort")?.value || "date-desc";
    const containers = [
        document.getElementById("movementsTableBody"),
        document.getElementById("movementsMobileList")
    ].filter(Boolean);

    containers.forEach(container => {
        const records = Array.from(container.querySelectorAll(".movement-record"));

        records.sort((a, b) => {
            if (sortValue === "date-asc") {
                return (a.dataset.date || "").localeCompare(b.dataset.date || "");
            }

            if (sortValue === "date-desc") {
                return (b.dataset.date || "").localeCompare(a.dataset.date || "");
            }

            if (sortValue === "sum-desc") {
                return Number(b.dataset.total || 0) - Number(a.dataset.total || 0);
            }

            if (sortValue === "sum-asc") {
                return Number(a.dataset.total || 0) - Number(b.dataset.total || 0);
            }

            return (a.dataset.name || "").localeCompare(
                b.dataset.name || "",
                "ru",
                {sensitivity:"base"}
            );
        });

        records.forEach(record => container.appendChild(record));
    });

    applyMovementFilters();
}

function resetMovementFilters() {
    activeMovementFilter = "all";

    document.querySelectorAll(".movements-tab").forEach(tab => {
        tab.classList.toggle("is-active", tab.dataset.filter === "all");
    });

    const search = document.getElementById("movementSearch");
    const dateFrom = document.getElementById("movementDateFrom");
    const dateTo = document.getElementById("movementDateTo");
    const sort = document.getElementById("movementSort");

    if (search) search.value = "";
    if (dateFrom) dateFrom.value = "";
    if (dateTo) dateTo.value = "";
    if (sort) sort.value = "date-desc";

    sortMovementRecords();
}

document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".movements-tab").forEach(button => {
        button.addEventListener("click", () => {
            activeMovementFilter = button.dataset.filter || "all";

            document.querySelectorAll(".movements-tab").forEach(tab => {
                tab.classList.toggle("is-active", tab === button);
            });

            applyMovementFilters();
        });
    });

    document.getElementById("movementSearch")?.addEventListener("input", applyMovementFilters);
    document.getElementById("movementDateFrom")?.addEventListener("change", applyMovementFilters);
    document.getElementById("movementDateTo")?.addEventListener("change", applyMovementFilters);
    document.getElementById("movementSort")?.addEventListener("change", sortMovementRecords);

    window.addEventListener("resize", applyMovementFilters);

    sortMovementRecords();
});