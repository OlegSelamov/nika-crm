const expenseModal = document.getElementById("expenseModal");
const expenseForm = document.getElementById("expenseForm");
const expenseModalTitle = document.getElementById("expenseModalTitle");
const expenseSubmitButton = document.getElementById("expenseSubmitButton");
const expenseAmountInput = document.getElementById("expenseAmount");
const expenseAmountPreview = document.getElementById("expenseModalAmountPreview");

function getLocalDateValue(date = new Date()) {
    const offset = date.getTimezoneOffset();
    return new Date(date.getTime() - offset * 60000).toISOString().slice(0, 10);
}

function formatExpenseAmount(value) {
    return `${new Intl.NumberFormat("ru-RU", {
        maximumFractionDigits: 2
    }).format(Number(value || 0))} ₸`;
}

function updateExpenseAmountPreview() {
    expenseAmountPreview.textContent = formatExpenseAmount(expenseAmountInput.value);
}

function showExpenseModal() {
    expenseModal.classList.add("is-open");
    expenseModal.setAttribute("aria-hidden", "false");
    document.body.classList.add("expense-modal-open");

    setTimeout(() => {
        document.getElementById("expenseDescription").focus();
    }, 50);
}

function openExpenseModal() {
    expenseForm.reset();
    expenseForm.action = "/expenses/add";
    expenseModalTitle.textContent = "Новый расход";
    expenseSubmitButton.textContent = "Сохранить расход";

    document.getElementById("expenseDate").value = getLocalDateValue();
    document.getElementById("expensePaymentMethod").value = "Наличные";

    updateExpenseAmountPreview();
    showExpenseModal();
}

function openEditExpenseModal(expense) {
    expenseForm.reset();
    expenseForm.action = `/expenses/${expense.id}/edit`;
    expenseModalTitle.textContent = "Редактирование расхода";
    expenseSubmitButton.textContent = "Сохранить изменения";

    document.getElementById("expenseDate").value = expense.date || getLocalDateValue();
    document.getElementById("expenseCategory").value = expense.category || "";
    document.getElementById("expenseDescription").value = expense.description || "";
    document.getElementById("expenseAmount").value = expense.amount || "";
    document.getElementById("expensePaymentMethod").value = expense.payment_method || "Наличные";
    document.getElementById("expenseComment").value = expense.comment || "";

    updateExpenseAmountPreview();
    showExpenseModal();
}

function closeExpenseModal() {
    expenseModal.classList.remove("is-open");
    expenseModal.setAttribute("aria-hidden", "true");
    document.body.classList.remove("expense-modal-open");
}

function applyQuickPeriod(period) {
    const form = document.querySelector(".expense-filter-panel");
    const fromInput = form.querySelector('[name="date_from"]');
    const toInput = form.querySelector('[name="date_to"]');

    const now = new Date();
    let start = new Date(now);
    let end = new Date(now);

    if (period === "week") {
        start.setDate(now.getDate() - 6);
    }

    if (period === "month") {
        start = new Date(now.getFullYear(), now.getMonth(), 1);
    }

    if (period === "previous-month") {
        start = new Date(now.getFullYear(), now.getMonth() - 1, 1);
        end = new Date(now.getFullYear(), now.getMonth(), 0);
    }

    fromInput.value = getLocalDateValue(start);
    toInput.value = getLocalDateValue(end);
    form.submit();
}

document.addEventListener("DOMContentLoaded", function () {
    if (expenseModal && expenseModal.parentElement !== document.body) {
        document.body.appendChild(expenseModal);
    }

    expenseAmountInput?.addEventListener("input", updateExpenseAmountPreview);

    document.querySelectorAll(".quick-periods button").forEach(button => {
        button.addEventListener("click", () => applyQuickPeriod(button.dataset.period));
    });

    const expenseMainCard = document.querySelector(".expense-main-card");
    const viewButtons = document.querySelectorAll(".expense-view-switch button");
    const savedExpenseView = localStorage.getItem("expenseView") || "list";

    function setExpenseView(view) {
        const compact = view === "compact";

        expenseMainCard?.classList.toggle("is-compact", compact);

        viewButtons.forEach(item => {
            item.classList.toggle("is-active", item.dataset.view === view);
        });

        localStorage.setItem("expenseView", view);
    }

    setExpenseView(savedExpenseView);

    viewButtons.forEach(button => {
        button.addEventListener("click", function () {
            setExpenseView(this.dataset.view || "list");
        });
    });
});

document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && expenseModal?.classList.contains("is-open")) {
        closeExpenseModal();
    }
});