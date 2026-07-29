const reportsPage = document.querySelector('.reports-page');
let currentReportType = reportsPage?.dataset.activeReport || 'sales';
const defaultReportDateFrom = reportsPage?.dataset.dateFrom || '';
const defaultReportDateTo = reportsPage?.dataset.dateTo || '';
const reportPrintMode = reportsPage?.dataset.printMode === '1';

function reportParams() {
    const from = document.getElementById('reportDateFrom')?.value || defaultReportDateFrom;
    const to = document.getElementById('reportDateTo')?.value || defaultReportDateTo;
    return new URLSearchParams({
        type: currentReportType,
        date_from: from,
        date_to: to
    });
}

function selectReport(type, button) {
    currentReportType = type;
    document.querySelectorAll('.report-tool').forEach(el => el.classList.remove('is-active'));
    if (button) button.classList.add('is-active');
    loadCurrentReport();
}

function formatCell(key, value) {
    if (value === null || value === undefined || value === '') return '—';

    const moneyKeys = [
        'amount','revenue','profit','gross_profit',
        'purchase_price','retail_price','stock_cost','total'
    ];

    if (moneyKeys.includes(key)) {
        return new Intl.NumberFormat('ru-RU', {
            maximumFractionDigits: 0
        }).format(Number(value || 0)) + ' ₸';
    }

    return String(value);
}

async function loadCurrentReport() {
    const loader = document.getElementById('reportsLoader');
    const empty = document.getElementById('reportsEmpty');
    if (loader) loader.style.display = 'inline';

    try {
        const response = await fetch('/reports/data?' + reportParams().toString());
        const data = await response.json();

        if (!data.success) throw new Error(data.error || 'Ошибка загрузки');

        document.getElementById('reportResultTitle').textContent = data.title;

        document.getElementById('reportsTableHead').innerHTML =
            '<tr>' + data.columns.map(c => `<th>${c.label}</th>`).join('') + '</tr>';

        document.getElementById('reportsTableBody').innerHTML =
            data.rows.map(row =>
                '<tr>' + data.columns.map(c =>
                    `<td>${formatCell(c.key, row[c.key])}</td>`
                ).join('') + '</tr>'
            ).join('');

        if (empty) empty.style.display = data.rows.length ? 'none' : 'grid';
    } catch (error) {
        document.getElementById('reportsTableHead').innerHTML = '';
        document.getElementById('reportsTableBody').innerHTML = '';
        if (empty) {
            empty.style.display = 'grid';
            const title = empty.querySelector('strong');
            const note = empty.querySelector('p');
            if (title) title.textContent = 'Не удалось загрузить отчёт';
            if (note) note.textContent = error.message;
        }
    } finally {
        if (loader) loader.style.display = 'none';
    }
}

function exportCurrentReport() {
    window.location.href = '/reports/export.xlsx?' + reportParams().toString();
}

function printCurrentReport() {
    window.open('/reports/print?' + reportParams().toString(), '_blank');
}

if (reportPrintMode) {
    window.addEventListener('load', () => window.print());
} else {
    document.addEventListener('DOMContentLoaded', loadCurrentReport);
}