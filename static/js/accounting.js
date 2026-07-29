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