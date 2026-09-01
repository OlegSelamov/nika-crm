(function () {
    document.querySelectorAll('.accounting-modal').forEach(function (modal) {
        if (modal.parentElement !== document.body) {
            document.body.appendChild(modal);
        }
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
            document.querySelectorAll('.accounting-modal.is-open').forEach(function (modal) {
                closeAccountingModal(modal.id);
            });
        }
    });

    document.addEventListener('click', function (event) {
        if (!event.target.closest('.document-menu-btn') &&
            !event.target.closest('.document-menu')) {
            closeAllDocumentMenus();
        }
    });

    var todayInputs = document.querySelectorAll('input[type="date"]');
    var today = new Date().toISOString().split('T')[0];
    todayInputs.forEach(function (input) {
        if (!input.value) input.value = today;
    });
})();

function openAccountingModal(id) {
    var modal = document.getElementById(id);
    if (!modal) return;
    modal.classList.add('is-open');
    modal.setAttribute('aria-hidden', 'false');
    document.body.classList.add('accounting-modal-open');

    window.setTimeout(function () {
        var firstInput = modal.querySelector('input:not([type="hidden"]), select, textarea');
        if (firstInput) firstInput.focus();
    }, 50);
}

function closeAccountingModal(id) {
    var modal = document.getElementById(id);
    if (!modal) return;
    modal.classList.remove('is-open');
    modal.setAttribute('aria-hidden', 'true');

    if (!document.querySelector('.accounting-modal.is-open')) {
        document.body.classList.remove('accounting-modal-open');
    }
}

function openReportModal(formType, title) {
    document.getElementById('reportFormType').value = formType;
    document.getElementById('reportModalTitle').textContent = title;
    openAccountingModal('reportModal');
}

function scrollToAccountingBlock(id) {
    var block = document.getElementById(id);
    if (block) block.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function setDocumentFilter(type) {
    var filter = document.getElementById('accountingDocumentFilter');
    if (filter) {
        filter.value = type;
        filterAccountingDocuments();
    }
    scrollToAccountingBlock('documentsBlock');
}

function filterAccountingDocuments() {
    var search = document.getElementById('accountingDocumentSearch');
    var filter = document.getElementById('accountingDocumentFilter');
    var query = search ? search.value.trim().toLowerCase() : '';
    var type = filter ? filter.value : 'all';
    var rows = document.querySelectorAll('.accounting-document-row');
    var visibleCount = 0;

    rows.forEach(function (row) {
        var rowSearch = (row.dataset.search || '').toLowerCase();
        var rowType = row.dataset.type || 'other';
        var matchesSearch = !query || rowSearch.includes(query);
        var matchesType = type === 'all' || rowType === type;
        var visible = matchesSearch && matchesType;

        row.style.display = visible ? '' : 'none';
        if (visible) visibleCount += 1;
    });

    var empty = document.getElementById('accountingFilteredEmpty');
    if (empty) {
        empty.style.display = visibleCount === 0 ? 'grid' : 'none';
    }
}


function filterAccountingOperations() {
    var search = document.getElementById('accountingOperationSearch');
    var filter = document.getElementById('accountingOperationFilter');
    var query = search ? search.value.trim().toLowerCase() : '';
    var type = filter ? filter.value : 'all';
    var rows = document.querySelectorAll('.accounting-operation-row');
    var visible = 0;

    rows.forEach(function (row) {
        var matchesSearch = !query || (row.dataset.search || '').includes(query);
        var matchesType = type === 'all' || row.dataset.type === type;
        var show = matchesSearch && matchesType;
        row.style.display = show ? '' : 'none';
        if (show) visible += 1;
    });

    var empty = document.getElementById('accountingOperationsEmpty');
    if (empty) empty.style.display = visible === 0 ? 'grid' : 'none';
}

function toggleDocumentMenu(button) {
    var menu = button.nextElementSibling;
    var wasOpen = menu && menu.classList.contains('is-open');
    closeAllDocumentMenus();
    if (menu && !wasOpen) menu.classList.add('is-open');
}

function closeAllDocumentMenus() {
    document.querySelectorAll('.document-menu.is-open').forEach(function (menu) {
        menu.classList.remove('is-open');
    });
}

function openEditDocumentModal(documentId) {
    document.getElementById('documentId').value = documentId;
    document.getElementById('documentModalTitle').textContent = 'Редактировать документ';

    var form = document.querySelector('#documentModal form');
    form.action = '/accounting/documents/' + encodeURIComponent(documentId) + '/edit';

    openAccountingModal('documentModal');
}
// --- Единый журнал продаж и документов ---
let accountingSaleMode = 'receipt';
let accountingSalesCache = null;

function getAccountingSalesData() {
    if (accountingSalesCache) return accountingSalesCache;
    const node = document.getElementById('accountingSalesData');
    if (!node) return [];
    try {
        accountingSalesCache = JSON.parse(node.textContent || '[]');
    } catch (error) {
        console.error('ACCOUNTING SALES DATA ERROR', error);
        accountingSalesCache = [];
    }
    return accountingSalesCache;
}

function accountingEscape(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function accountingMoney(value) {
    const amount = Number(value || 0);
    return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(amount) + ' ₸';
}

function switchAccountingSaleMode(mode) {
    accountingSaleMode = mode === 'invoice' ? 'invoice' : 'receipt';
    document.querySelectorAll('[data-accounting-sale-mode]').forEach(function (button) {
        const active = button.dataset.accountingSaleMode === accountingSaleMode;
        button.classList.toggle('is-active', active);
        button.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
    filterAccountingSales();
}

function filterAccountingSales() {
    const search = document.getElementById('accountingSaleSearch');
    const query = search ? search.value.trim().toLowerCase() : '';
    const rows = document.querySelectorAll('.accounting-sale-row');
    let visible = 0;

    rows.forEach(function (row) {
        const matchesMode = row.dataset.mode === accountingSaleMode;
        const matchesSearch = !query || (row.dataset.search || '').toLowerCase().includes(query);
        const show = matchesMode && matchesSearch;
        row.style.display = show ? '' : 'none';
        if (show) visible += 1;
    });

    const empty = document.getElementById('accountingSalesEmpty');
    if (empty) empty.style.display = visible === 0 ? 'grid' : 'none';
}

function accountingDocumentButton(url, title, meta, kind) {
    if (!url) return '';
    return `
        <a class="accounting-sale-document ${kind ? 'accounting-sale-document--' + kind : ''}"
           href="${accountingEscape(url)}" target="_blank" rel="noopener">
            <span class="accounting-sale-document__icon">${kind === 'esf' ? 'ЭСФ' : '📄'}</span>
            <span class="accounting-sale-document__text">
                <strong>${accountingEscape(title)}</strong>
                ${meta ? `<small>${accountingEscape(meta)}</small>` : ''}
            </span>
            <span class="accounting-sale-document__arrow">›</span>
        </a>`;
}

function openAccountingSaleDocuments(saleId) {
    const sale = getAccountingSalesData().find(function (item) {
        return Number(item.id) === Number(saleId);
    });
    if (!sale) return;

    const title = document.getElementById('saleDocumentsModalTitle');
    const subtitle = document.getElementById('saleDocumentsModalSubtitle');
    const body = document.getElementById('saleDocumentsModalBody');
    if (!title || !subtitle || !body) return;

    title.textContent = `Продажа №${sale.number}`;
    subtitle.textContent = `${sale.client_primary} · ${sale.date} · ${accountingMoney(sale.amount)}`;

    const productBlock = Number(sale.product_count || 0) > 0 ? `
        <section class="accounting-sale-doc-section">
            <div class="accounting-sale-doc-section__title">
                <strong>Документы по товарам</strong>
                <span>${sale.product_count} поз. · ${accountingMoney(sale.product_total)}</span>
            </div>
            <div class="accounting-sale-doc-grid">
                ${accountingDocumentButton(sale.waybill_url, 'Накладная', `${sale.product_count} товарных позиций`, 'product')}
            </div>
        </section>` : '';

    const serviceBlock = Number(sale.service_count || 0) > 0 ? `
        <section class="accounting-sale-doc-section">
            <div class="accounting-sale-doc-section__title">
                <strong>Документы по услугам</strong>
                <span>${sale.service_count} поз. · ${accountingMoney(sale.service_total)}</span>
            </div>
            <div class="accounting-sale-doc-grid">
                ${accountingDocumentButton(sale.act_url, 'Акт выполненных работ', `${sale.service_count} услуг`, 'service')}
            </div>
        </section>` : '';

    const esfMetaParts = [];
    if (sale.esf_status_label) esfMetaParts.push(sale.esf_status_label);
    if (sale.esf_registration_number) esfMetaParts.push(`№ ${sale.esf_registration_number}`);
    else if (sale.esf_external_id) esfMetaParts.push(`ID ${sale.esf_external_id}`);
    const esfTitle = sale.esf_status ? 'ЭСФ' : 'Сформировать ЭСФ';

    body.innerHTML = `
        <section class="accounting-sale-doc-section">
            <div class="accounting-sale-doc-section__title"><strong>Основной документ</strong></div>
            <div class="accounting-sale-doc-grid">
                ${accountingDocumentButton(sale.main_url, sale.main_title, sale.status_label, 'main')}
            </div>
        </section>
        ${productBlock}
        ${serviceBlock}
        <section class="accounting-sale-doc-section">
            <div class="accounting-sale-doc-section__title"><strong>Общие документы</strong><span>На всю продажу</span></div>
            <div class="accounting-sale-doc-grid">
                ${accountingDocumentButton(sale.invoice_facture_url, 'Счёт-фактура', accountingMoney(sale.amount), 'common')}
            </div>
        </section>
        <section class="accounting-sale-doc-section">
            <div class="accounting-sale-doc-section__title"><strong>Электронные документы</strong><span>ИС ЭСФ</span></div>
            <div class="accounting-sale-doc-grid">
                ${accountingDocumentButton(sale.esf_url, esfTitle, esfMetaParts.join(' · '), 'esf')}
            </div>
        </section>`;

    openAccountingModal('saleDocumentsModal');
}

// Страница открывается сразу в привычном режиме «Чеки».
document.addEventListener('DOMContentLoaded', function () {
    switchAccountingSaleMode('receipt');
});
