(() => {
    const modal = document.getElementById('supplierModal');
    const form = document.getElementById('supplierForm');
    const lookupButton = document.getElementById('supplierLookupBtn');
    const lookupStatus = document.getElementById('supplierLookupStatus');

    // The page content lives inside transformed/layout containers. A fixed
    // modal left there is positioned against that inner block instead of the
    // browser viewport. Move it to body once so the backdrop covers the whole
    // screen, including the sidebar/topbar, and centering uses the viewport.
    if (modal && modal.parentElement !== document.body) {
        document.body.appendChild(modal);
    }

    function ensureSupplierMenuLink() {
        if (document.querySelector('.sidebar a[href="/suppliers"]')) return;
        const incomeLink = document.querySelector('.sidebar a[href="/stock/income"]');
        if (!incomeLink) return;

        const link = document.createElement('a');
        link.href = '/suppliers';
        link.className = 'menu-link active-menu-item';
        link.innerHTML = '<img src="/static/icons/company.png" class="menu-icon"><span class="text">Поставщики</span>';
        incomeLink.parentNode.insertBefore(link, incomeLink);
    }

    function payload() {
        return {
            name: document.getElementById('supplierName').value.trim(),
            bin_iin: document.getElementById('supplierBin').value.trim(),
            contact_name: document.getElementById('supplierContact').value.trim(),
            phone: document.getElementById('supplierPhone').value.trim(),
            email: document.getElementById('supplierEmail').value.trim(),
            address: document.getElementById('supplierAddress').value.trim(),
            comment: document.getElementById('supplierComment').value.trim(),
        };
    }

    function showLookupStatus(message, type = 'info') {
        if (!lookupStatus) return;
        lookupStatus.hidden = false;
        lookupStatus.className = `supplier-lookup-status ${type}`;
        lookupStatus.textContent = message;
    }

    function clearLookupStatus() {
        if (!lookupStatus) return;
        lookupStatus.hidden = true;
        lookupStatus.className = 'supplier-lookup-status';
        lookupStatus.textContent = '';
    }

    async function lookupSupplier() {
        const binInput = document.getElementById('supplierBin');
        const identifier = String(binInput?.value || '').replace(/\D/g, '');
        if (binInput) binInput.value = identifier;

        if (identifier.length !== 12) {
            showLookupStatus('Введите корректный БИН / ИИН из 12 цифр.', 'error');
            binInput?.focus();
            return;
        }

        lookupButton.disabled = true;
        lookupButton.textContent = 'Ищем…';
        showLookupStatus('Ищем данные в подключённых справочниках…', 'info');

        try {
            const response = await fetch('/api/clients/lookup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
                body: JSON.stringify({ identifier }),
            });
            const result = await response.json().catch(() => ({}));

            if (!response.ok || !result.found || !result.data) {
                showLookupStatus(result.message || 'Данные не найдены. Заполните поставщика вручную.', 'error');
                return;
            }

            const data = result.data || {};
            const name = data.company_name || data.full_name || '';
            const contact = data.full_name || '';

            if (name) document.getElementById('supplierName').value = name;
            if (contact && contact !== name) document.getElementById('supplierContact').value = contact;
            if (data.phone) document.getElementById('supplierPhone').value = data.phone;
            if (data.address) document.getElementById('supplierAddress').value = data.address;
            if (data.iin) document.getElementById('supplierBin').value = data.iin;

            showLookupStatus(result.message || 'Данные найдены и подставлены.', 'ok');
            document.getElementById('supplierName')?.focus();
        } catch (error) {
            console.error('SUPPLIER LOOKUP ERROR:', error);
            showLookupStatus('Не удалось выполнить поиск. Данные можно заполнить вручную.', 'error');
        } finally {
            lookupButton.disabled = false;
            lookupButton.textContent = 'Найти';
        }
    }

    window.openSupplierModal = function (supplier = null) {
        form.reset();
        clearLookupStatus();
        document.getElementById('supplierId').value = supplier?.id || '';
        document.getElementById('supplierModalTitle').textContent = supplier ? 'Изменить поставщика' : 'Новый поставщик';
        if (supplier) {
            document.getElementById('supplierName').value = supplier.name || '';
            document.getElementById('supplierBin').value = supplier.bin_iin || '';
            document.getElementById('supplierContact').value = supplier.contact_name || '';
            document.getElementById('supplierPhone').value = supplier.phone || '';
            document.getElementById('supplierEmail').value = supplier.email || '';
            document.getElementById('supplierAddress').value = supplier.address || '';
            document.getElementById('supplierComment').value = supplier.comment || '';
        }
        modal.hidden = false;
        document.body.style.overflow = 'hidden';
        setTimeout(() => (supplier ? document.getElementById('supplierName') : document.getElementById('supplierBin'))?.focus(), 30);
    };

    window.closeSupplierModal = function () {
        modal.hidden = true;
        document.body.style.overflow = '';
    };

    window.editSupplierFromButton = function (button) {
        try {
            window.openSupplierModal(JSON.parse(button.dataset.supplier || '{}'));
        } catch (error) {
            console.error(error);
        }
    };

    window.archiveSupplier = async function (id, name) {
        if (!confirm(`Архивировать поставщика «${name}»? Старые приходы сохранят связь с ним.`)) return;
        const response = await fetch(`/api/suppliers/${id}`, { method: 'DELETE' });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.success) {
            alert(data.error || 'Не удалось архивировать поставщика');
            return;
        }
        location.reload();
    };

    lookupButton?.addEventListener('click', lookupSupplier);
    document.getElementById('supplierBin')?.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
            event.preventDefault();
            lookupSupplier();
        }
    });
    document.getElementById('supplierBin')?.addEventListener('input', function () {
        this.value = this.value.replace(/\D/g, '').slice(0, 12);
        clearLookupStatus();
    });

    form?.addEventListener('submit', async (event) => {
        event.preventDefault();
        const id = document.getElementById('supplierId').value;
        const response = await fetch(id ? `/api/suppliers/${id}` : '/api/suppliers', {
            method: id ? 'PUT' : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload()),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.success) {
            alert(data.error || 'Не удалось сохранить поставщика');
            return;
        }
        location.reload();
    });

    document.getElementById('supplierSearch')?.addEventListener('input', function () {
        const q = this.value.trim().toLowerCase();
        document.querySelectorAll('.supplier-row').forEach(row => {
            row.style.display = !q || (row.dataset.search || '').includes(q) ? '' : 'none';
        });
    });

    modal?.addEventListener('click', (event) => {
        if (event.target === modal) window.closeSupplierModal();
    });

    ensureSupplierMenuLink();
})();
