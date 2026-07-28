const css = getComputedStyle(document.documentElement);

const labels = {{ chart_labels|default([])|tojson }};
const revenueValues = {{ chart_values|default([])|tojson }};
const profitValues = {{ profit_chart_values|default([])|tojson }};
const expenseValues = {{ expense_chart_values|default([])|tojson }};

new Chart(document.getElementById("businessChart"), {
    type: "line",
    data: {
        labels,
        datasets: [
            {
                label: "Выручка",
                data: revenueValues,
                borderColor: "#6f57ff",
                backgroundColor: "rgba(111,87,255,.10)",
                fill: true,
                borderWidth: 3,
                tension: .38,
                pointRadius: 2,
                pointHoverRadius: 5
            },
            {
                label: "Прибыль",
                data: profitValues,
                borderColor: "#17a779",
                backgroundColor: "rgba(23,167,121,.06)",
                fill: false,
                borderWidth: 2,
                tension: .38,
                pointRadius: 2
            },
            {
                label: "Расходы",
                data: expenseValues,
                borderColor: "#dc6074",
                backgroundColor: "rgba(220,96,116,.06)",
                fill: false,
                borderWidth: 2,
                tension: .38,
                pointRadius: 2
            }
        ]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
            legend: { display: false },
            tooltip: {
                callbacks: {
                    label(context) {
                        return `${context.dataset.label}: ${new Intl.NumberFormat("ru-RU").format(context.raw || 0)} ₸`;
                    }
                }
            }
        },
        scales: {
            x: { grid: { display: false }, ticks: { color: "#8a91a3", maxRotation: 0 } },
            y: {
                beginAtZero: true,
                grid: { color: "rgba(125,132,151,.10)" },
                ticks: {
                    color: "#8a91a3",
                    callback(value) {
                        return new Intl.NumberFormat("ru-RU", { notation: "compact" }).format(value);
                    }
                }
            }
        }
    }
});

new Chart(document.getElementById("paymentsChart"), {
    type: "doughnut",
    data: {
        labels: ["Наличные", "Карта", "Kaspi"],
        datasets: [{
			data: [
				{{ payments.cash or 0 }},
				{{ payments.card or 0 }},
				{{ payments.kaspi or 0 }}
			],
            backgroundColor: ["#6f57ff", "#20a7d8", "#e9578f"],
            borderColor: "#ffffff",
            borderWidth: 4,
            hoverOffset: 6
        }]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "72%",
        plugins: { legend: { display: false } }
    }
});

const expenseCategoryLabels = {{ expense_categories|default([])|map(attribute='category')|list|tojson }};
const expenseCategoryValues = {{ expense_categories|default([])|map(attribute='total')|list|tojson }};

new Chart(document.getElementById("expensesChart"), {
    type: "doughnut",
    data: {
        labels: expenseCategoryLabels.length ? expenseCategoryLabels : ["Закупки", "Зарплата", "Налоги"],
        datasets: [{
            data: expenseCategoryValues.length ? expenseCategoryValues : [
                {{ purchase_total }},
                {{ salary_total }},
                {{ taxes_total }}
            ],
            backgroundColor: ["#6f57ff", "#20a7d8", "#e9578f", "#f2a34a", "#17a779", "#8a91a3", "#b65bd5"],
            borderColor: "#ffffff",
            borderWidth: 3
        }]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "68%",
        plugins: {
            legend: {
                position: "bottom",
                labels: { boxWidth: 9, usePointStyle: true, font: { size: 10 } }
            }
        }
    }
});

function localDate(date) {
    const offset = date.getTimezoneOffset();
    return new Date(date.getTime() - offset * 60000).toISOString().slice(0, 10);
}

function applyAnalyticsPeriod(period) {
    const form = document.querySelector(".analytics-period-form");
    const from = form.querySelector('[name="from"]');
    const to = form.querySelector('[name="to"]');
    const now = new Date();

    let start = new Date(now);
    let end = new Date(now);

    if (period === "week") {
        start.setDate(now.getDate() - 6);
    } else if (period === "month") {
        start = new Date(now.getFullYear(), now.getMonth(), 1);
    } else if (period === "previous-month") {
        start = new Date(now.getFullYear(), now.getMonth() - 1, 1);
        end = new Date(now.getFullYear(), now.getMonth(), 0);
    } else if (period === "year") {
        start = new Date(now.getFullYear(), 0, 1);
    }

    from.value = localDate(start);
    to.value = localDate(end);
    form.submit();
}

document.querySelectorAll(".analytics-period-presets button").forEach(button => {
    button.addEventListener("click", () => applyAnalyticsPeriod(button.dataset.period));
});