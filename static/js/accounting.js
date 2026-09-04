(function () {
    mountAccountingDocumentPreview();

    document.querySelectorAll('.accounting-modal').forEach(function (modal) {
        if (modal.parentElement !== document.body) {
            document.body.appendChild(modal);
        }
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
            var preview = document.getElementById('accountingDocumentPreviewModal');
            if (preview && preview.classList.contains('is-open')) {
                closeAccountingDocumentPreview();
                return;
            }
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
let accountingDocumentState = null;

function mountAccountingDocumentPreview() {
    let modal = document.getElementById('accountingDocumentPreviewModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.className = 'accounting-modal accounting-document-modal';
        modal.id = 'accountingDocumentPreviewModal';
        modal.setAttribute('aria-hidden', 'true');
        modal.innerHTML = `
            <div class="accounting-modal__backdrop" onclick="closeAccountingDocumentPreview()"></div>
            <div class="accounting-modal__dialog accounting-modal__dialog--document" role="dialog" aria-modal="true" aria-labelledby="accountingDocumentPreviewTitle">
                <div class="accounting-modal__head accounting-document-modal__head">
                    <div>
                        <h3 id="accountingDocumentPreviewTitle">Документ</h3>
                        <p id="accountingDocumentPreviewSubtitle">Предварительный просмотр</p>
                    </div>
                    <button type="button" onclick="closeAccountingDocumentPreview()" aria-label="Закрыть">×</button>
                </div>
                <div class="accounting-document-modal__body" id="accountingDocumentPreviewBody">
                    <div class="accounting-document-modal__loading">Загрузка документа…</div>
                </div>
                <div class="accounting-document-modal__footer">
                    <button type="button" onclick="printAccountingDocument()">Печать</button>
                    <button type="button" id="accountingDocumentDownloadBtn" onclick="downloadAccountingDocument()">Скачать PDF</button>
                    <button type="button" onclick="shareAccountingDocument()">Поделиться</button>
                    <button type="button" class="accounting-document-modal__close" onclick="closeAccountingDocumentPreview()">Закрыть</button>
                </div>
            </div>`;
    }
    if (modal.parentElement !== document.body) document.body.appendChild(modal);
    return modal;
}

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

function setAccountingSalesListCollapsed(collapsed, remember) {
    const section = document.getElementById('salesDocumentsBlock');
    const content = document.getElementById('accountingSalesContent');
    const button = document.getElementById('accountingSalesCollapseBtn');
    if (!section || !content || !button) return;

    const isCollapsed = Boolean(collapsed);
    section.classList.toggle('is-sales-collapsed', isCollapsed);
    content.hidden = isCollapsed;
    button.setAttribute('aria-expanded', isCollapsed ? 'false' : 'true');

    const icon = button.querySelector('span');
    const label = button.querySelector('b');
    if (icon) icon.textContent = isCollapsed ? '⌄' : '⌃';
    if (label) label.textContent = isCollapsed ? 'Показать список' : 'Скрыть список';

    if (remember !== false) {
        try {
            window.localStorage.setItem('nika-accounting-sales-collapsed', isCollapsed ? '1' : '0');
        } catch (error) {
            console.warn('ACCOUNTING LIST STATE ERROR', error);
        }
    }
}

function toggleAccountingSalesList() {
    const content = document.getElementById('accountingSalesContent');
    if (!content) return;
    setAccountingSalesListCollapsed(!content.hidden, true);
}

function restoreAccountingSalesListState() {
    let collapsed = false;
    try {
        collapsed = window.localStorage.getItem('nika-accounting-sales-collapsed') === '1';
    } catch (error) {
        console.warn('ACCOUNTING LIST STATE ERROR', error);
    }
    setAccountingSalesListCollapsed(collapsed, false);
}

function accountingDocumentButton(saleId, key, url, title, meta, kind) {
    if (!url) return '';
    if (kind === 'esf') {
        return `
        <button type="button" class="accounting-sale-document accounting-sale-document--esf"
                onclick="window.location.href='${accountingEscape(url)}'">
            <span class="accounting-sale-document__icon">ЭСФ</span>
            <span class="accounting-sale-document__text">
                <strong>${accountingEscape(title)}</strong>
                ${meta ? `<small>${accountingEscape(meta)}</small>` : ''}
            </span>
            <span class="accounting-sale-document__arrow">›</span>
        </button>`;
    }
    return `
        <button type="button" class="accounting-sale-document ${kind ? 'accounting-sale-document--' + kind : ''}"
                onclick="openAccountingDocumentFromSale(${Number(saleId)}, '${accountingEscape(key)}')">
            <span class="accounting-sale-document__icon">📄</span>
            <span class="accounting-sale-document__text">
                <strong>${accountingEscape(title)}</strong>
                ${meta ? `<small>${accountingEscape(meta)}</small>` : ''}
            </span>
            <span class="accounting-sale-document__arrow">›</span>
        </button>`;
}

function getAccountingSale(saleId) {
    return getAccountingSalesData().find(function (item) {
        return Number(item.id) === Number(saleId);
    });
}

function accountingSaleDocumentConfig(sale, key) {
    if (!sale) return null;

    const configs = {
        waybill: {
            url: sale.waybill_url,
            title: 'Накладная',
            type: 'nakladnaya',
            filename: `nakladnaya-${sale.id}.pdf`
        },
        act: {
            url: sale.act_url,
            title: 'Акт выполненных работ',
            type: 'act',
            filename: `akt-vypolnennyh-rabot-${sale.id}.pdf`
        },
        invoiceFacture: {
            url: sale.invoice_facture_url,
            title: 'Счёт-фактура',
            type: 'schet-factura',
            filename: `schet-factura-${sale.id}.pdf`
        }
    };

    if (key === 'main') {
        let type = 'check';
        let filename = `check-${sale.id}.pdf`;
        if ((sale.main_url || '').includes('/refund-check/')) {
            type = 'refund-check';
            filename = `refund-check-${sale.id}.pdf`;
        } else if ((sale.main_url || '').includes('/invoice/')) {
            type = 'invoice';
            filename = `schet-na-oplatu-${sale.id}.pdf`;
        }
        return {
            url: sale.main_url,
            title: sale.main_title || sale.main_label || 'Документ',
            type: type,
            filename: filename
        };
    }

    return configs[key] || null;
}

function openAccountingSaleMain(saleId) {
    openAccountingDocumentFromSale(saleId, 'main', false);
}

function openAccountingDocumentFromSale(saleId, key, returnToDocuments) {
    const sale = getAccountingSale(saleId);
    const config = accountingSaleDocumentConfig(sale, key);
    if (!sale || !config || !config.url) {
        alert('Документ продажи не найден. Обновите данные бухгалтерии и повторите попытку.');
        return;
    }

    openAccountingDocumentPreview({
        url: config.url,
        pdfUrl: `/docs/pdf/${config.type}/${sale.id}`,
        title: config.title,
        subtitle: `Продажа №${sale.number} · ${sale.date}`,
        filename: config.filename,
        returnModalId: returnToDocuments === false ? '' : 'saleDocumentsModal'
    });
}

function accountingDocumentConfigFromUrl(url, title, subtitle) {
    const cleanUrl = String(url || '').trim();
    if (!cleanUrl) return null;

    let pathname = cleanUrl;
    try {
        pathname = new URL(cleanUrl, window.location.origin).pathname;
    } catch (error) {
        console.warn('ACCOUNTING DOCUMENT URL ERROR', error);
    }

    const match = pathname.match(/\/docs\/(check|refund-check|invoice|nakladnaya|schet-factura|act)\/(\d+)/);
    if (!match) {
        const rawFilename = decodeURIComponent(pathname.split('/').pop() || 'document');
        return {
            url: cleanUrl,
            downloadUrl: cleanUrl,
            title: title || 'Документ',
            subtitle: subtitle || 'Загруженный файл',
            filename: rawFilename,
            isUploadedFile: true
        };
    }

    const type = match[1];
    const documentId = match[2];
    const labels = {
        'check': 'Чек',
        'refund-check': 'Чек возврата',
        'invoice': 'Счёт на оплату',
        'nakladnaya': 'Накладная',
        'schet-factura': 'Счёт-фактура',
        'act': 'Акт выполненных работ'
    };
    const filenames = {
        'check': `check-${documentId}.pdf`,
        'refund-check': `refund-check-${documentId}.pdf`,
        'invoice': `schet-na-oplatu-${documentId}.pdf`,
        'nakladnaya': `nakladnaya-${documentId}.pdf`,
        'schet-factura': `schet-factura-${documentId}.pdf`,
        'act': `akt-vypolnennyh-rabot-${documentId}.pdf`
    };
    return {
        url: cleanUrl,
        pdfUrl: `/docs/pdf/${type}/${documentId}`,
        title: title || labels[type] || 'Документ',
        subtitle: subtitle || 'Предварительный просмотр',
        filename: filenames[type] || `document-${documentId}.pdf`
    };
}

function openAccountingUrlDocument(url, title, subtitle) {
    const config = accountingDocumentConfigFromUrl(url, title, subtitle);
    if (!config) {
        alert('Ссылка на документ отсутствует.');
        return;
    }
    openAccountingDocumentPreview(config);
}

function openAccountingFile(url, title) {
    closeAllDocumentMenus();
    openAccountingUrlDocument(url, title, 'Загруженный файл');
}

function openAccountingDocumentPreview(options) {
    if (!options || !options.url) {
        alert('Не удалось определить адрес документа.');
        return;
    }
    mountAccountingDocumentPreview();
    const returnModalId = options.returnModalId || '';
    if (returnModalId) closeAccountingModal(returnModalId);

    accountingDocumentState = Object.assign({}, options);
    const title = document.getElementById('accountingDocumentPreviewTitle');
    const subtitle = document.getElementById('accountingDocumentPreviewSubtitle');
    const body = document.getElementById('accountingDocumentPreviewBody');
    const downloadBtn = document.getElementById('accountingDocumentDownloadBtn');

    if (title) title.textContent = options.title || 'Документ';
    if (subtitle) subtitle.textContent = options.subtitle || 'Предварительный просмотр';
    if (downloadBtn) downloadBtn.textContent = options.isUploadedFile ? 'Скачать файл' : 'Скачать PDF';
    if (body) {
        body.innerHTML = '';
        const frame = document.createElement('iframe');
        frame.id = 'accountingDocumentFrame';
        frame.title = options.title || 'Документ';
        frame.src = options.url;
        body.appendChild(frame);
    }
    openAccountingModal('accountingDocumentPreviewModal');
}

function closeAccountingDocumentPreview() {
    const returnModalId = accountingDocumentState && accountingDocumentState.returnModalId;
    closeAccountingModal('accountingDocumentPreviewModal');
    const body = document.getElementById('accountingDocumentPreviewBody');
    if (body) body.innerHTML = '<div class="accounting-document-modal__loading">Загрузка документа…</div>';
    accountingDocumentState = null;
    if (returnModalId) openAccountingModal(returnModalId);
}

function printAccountingDocument() {
    const frame = document.getElementById('accountingDocumentFrame');
    if (!frame || !frame.contentWindow) return;
    try {
        frame.contentWindow.focus();
        frame.contentWindow.print();
    } catch (error) {
        console.error('ACCOUNTING DOCUMENT PRINT ERROR', error);
        alert('Не удалось открыть печать документа');
    }
}

async function fetchAccountingDocumentBlob() {
    if (!accountingDocumentState) throw new Error('Документ не выбран');
    const url = accountingDocumentState.pdfUrl || accountingDocumentState.downloadUrl || accountingDocumentState.url;
    const response = await fetch(url, { credentials: 'same-origin' });
    if (!response.ok) throw new Error('Не удалось скачать документ');
    return response.blob();
}

function downloadAccountingBlob(blob, filename) {
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = objectUrl;
    link.download = filename || 'document';
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(function () { URL.revokeObjectURL(objectUrl); }, 1000);
}

async function downloadAccountingDocument() {
    if (!accountingDocumentState) return;
    try {
        const blob = await fetchAccountingDocumentBlob();
        downloadAccountingBlob(blob, accountingDocumentState.filename);
    } catch (error) {
        console.error('ACCOUNTING DOCUMENT DOWNLOAD ERROR', error);
        alert(error.message || 'Не удалось скачать документ');
    }
}

async function shareAccountingDocument() {
    if (!accountingDocumentState) return;
    try {
        const blob = await fetchAccountingDocumentBlob();
        const filename = accountingDocumentState.filename || 'document';
        if (navigator.share && navigator.canShare && typeof File !== 'undefined') {
            const file = new File([blob], filename, { type: blob.type || 'application/octet-stream' });
            if (navigator.canShare({ files: [file] })) {
                await navigator.share({ title: accountingDocumentState.title || 'Документ', files: [file] });
                return;
            }
        }
        downloadAccountingBlob(blob, filename);
        alert('Системная отправка недоступна. Файл скачан — его можно отправить вручную.');
    } catch (error) {
        if (error && error.name === 'AbortError') return;
        console.error('ACCOUNTING DOCUMENT SHARE ERROR', error);
        alert(error.message || 'Не удалось подготовить документ');
    }
}

function openAccountingSaleDocuments(saleId) {
    const sale = getAccountingSale(saleId);
    if (!sale) {
        alert('Продажа не найдена. Обновите страницу и повторите попытку.');
        return;
    }

    const title = document.getElementById('saleDocumentsModalTitle');
    const subtitle = document.getElementById('saleDocumentsModalSubtitle');
    const body = document.getElementById('saleDocumentsModalBody');
    if (!title || !subtitle || !body) {
        alert('Не удалось открыть список документов. Обновите страницу и повторите попытку.');
        return;
    }

    title.textContent = `Продажа №${sale.number}`;
    subtitle.textContent = `${sale.client_primary} · ${sale.date} · ${accountingMoney(sale.amount)}`;

    const productBlock = Number(sale.product_count || 0) > 0 ? `
        <section class="accounting-sale-doc-section">
            <div class="accounting-sale-doc-section__title">
                <strong>Документы по товарам</strong>
                <span>${sale.product_count} поз. · ${accountingMoney(sale.product_total)}</span>
            </div>
            <div class="accounting-sale-doc-grid">
                ${accountingDocumentButton(sale.id, 'waybill', sale.waybill_url, 'Накладная', `${sale.product_count} товарных позиций`, 'product')}
            </div>
        </section>` : '';

    const serviceBlock = Number(sale.service_count || 0) > 0 ? `
        <section class="accounting-sale-doc-section">
            <div class="accounting-sale-doc-section__title">
                <strong>Документы по услугам</strong>
                <span>${sale.service_count} поз. · ${accountingMoney(sale.service_total)}</span>
            </div>
            <div class="accounting-sale-doc-grid">
                ${accountingDocumentButton(sale.id, 'act', sale.act_url, 'Акт выполненных работ', `${sale.service_count} услуг`, 'service')}
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
                ${accountingDocumentButton(sale.id, 'main', sale.main_url, sale.main_title, sale.status_label, 'main')}
            </div>
        </section>
        ${productBlock}
        ${serviceBlock}
        <section class="accounting-sale-doc-section">
            <div class="accounting-sale-doc-section__title"><strong>Общие документы</strong><span>На всю продажу</span></div>
            <div class="accounting-sale-doc-grid">
                ${accountingDocumentButton(sale.id, 'invoiceFacture', sale.invoice_facture_url, 'Счёт-фактура', accountingMoney(sale.amount), 'common')}
            </div>
        </section>
        <section class="accounting-sale-doc-section">
            <div class="accounting-sale-doc-section__title"><strong>Электронные документы</strong><span>ИС ЭСФ</span></div>
            <div class="accounting-sale-doc-grid">
                ${accountingDocumentButton(sale.id, 'esf', sale.esf_url, esfTitle, esfMetaParts.join(' · '), 'esf')}
            </div>
        </section>`;

    openAccountingModal('saleDocumentsModal');
}

// Страница открывается сразу в привычном режиме «Чеки».
document.addEventListener('DOMContentLoaded', function () {
    restoreAccountingSalesListState();
    switchAccountingSaleMode('receipt');
});
