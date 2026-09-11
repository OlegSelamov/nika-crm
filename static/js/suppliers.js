(() => {
    const modal = document.getElementById('supplierModal');
    const form = document.getElementById('supplierForm');

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

    window.openSupplierModal = function (supplier = null) {
        form.reset();
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
        setTimeout(() => document.getElementById('supplierName').focus(), 30);
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
})();
