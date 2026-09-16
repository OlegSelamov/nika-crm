(() => {
    document.addEventListener('DOMContentLoaded', async () => {
        const form = document.getElementById('incomeForm');
        const grid = form?.querySelector('.income-form-grid');
        if (!form || !grid || document.getElementById('incomeSupplier')) return;

        const style = document.createElement('style');
        style.textContent = `
            .income-field--supplier{grid-column:1/-1}
            .income-supplier-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;align-items:center}
            .income-supplier-select{width:100%;height:48px;border:1px solid #e5e8f0;border-radius:11px;background:#fff;padding:0 13px;color:#303747;font-size:12px;outline:none}
            .income-supplier-select:focus{border-color:#b9afff;box-shadow:0 0 0 3px rgba(115,87,255,.08)}
            .income-supplier-link{height:48px;padding:0 14px;display:inline-flex;align-items:center;justify-content:center;border:1px solid #ddd8fb;border-radius:11px;background:#f4f1ff;color:#6655c8!important;font-size:10px;font-weight:900;text-decoration:none;white-space:nowrap}
            .income-supplier-error{color:#c43d4f!important;font-weight:800}
            @media(max-width:768px){.income-supplier-row{grid-template-columns:1fr}.income-supplier-link{height:42px}}
        `;
        document.head.appendChild(style);

        const field = document.createElement('div');
        field.className = 'income-field income-field--supplier';
        field.innerHTML = `
            <label for="incomeSupplier">Поставщик</label>
            <div class="income-supplier-row">
                <select id="incomeSupplier" name="supplier_id" class="income-supplier-select">
                    <option value="">Загрузка поставщиков…</option>
                </select>
                <a href="/suppliers" class="income-supplier-link">+ Поставщик</a>
            </div>
            <small id="incomeSupplierHint">Поставщик будет привязан к этому приходу товара</small>
        `;

        const productField = grid.querySelector('.income-field--product');
        grid.insertBefore(field, productField || grid.firstChild);
        form.action = '/stock/income/supplier';

        const headerActions = document.querySelector('.income-header-actions');
        if (headerActions && !headerActions.querySelector('a[href="/suppliers"]')) {
            const link = document.createElement('a');
            link.href = '/suppliers';
            link.className = 'income-btn income-btn--light';
            link.textContent = 'Поставщики';
            headerActions.prepend(link);
        }

        const select = document.getElementById('incomeSupplier');
        const hint = document.getElementById('incomeSupplierHint');
        const submit = form.querySelector('.income-submit');
        const defaultSubmitHtml = submit?.innerHTML || '';
        let suppliersReady = false;
        let suppliersLoadError = false;

        function setHint(message, isError = false) {
            if (!hint) return;
            hint.classList.toggle('income-supplier-error', isError);
            hint.innerHTML = message;
        }

        form.addEventListener('submit', event => {
            if (event.defaultPrevented) return;

            if (suppliersLoadError) {
                event.preventDefault();
                setHint('Не удалось загрузить поставщиков. Обновите страницу или откройте раздел «Поставщики».', true);
                select?.scrollIntoView({block: 'center', behavior: 'smooth'});
                return;
            }

            if (!suppliersReady || !select?.value) {
                event.preventDefault();
                setHint(
                    suppliersReady
                        ? 'Выберите поставщика перед сохранением прихода.'
                        : 'Сначала добавьте поставщика, затем оформляйте приход.',
                    true
                );
                select?.scrollIntoView({block: 'center', behavior: 'smooth'});
                if (!select?.disabled) select?.focus();
                return;
            }

            if (submit) {
                submit.disabled = true;
                submit.innerHTML = '<span>…</span> Сохраняю приход';
            }
        });

        select?.addEventListener('change', () => {
            if (select.value) {
                setHint('Поставщик будет привязан к этому приходу товара');
            }
            if (submit?.disabled && suppliersReady) {
                submit.disabled = false;
                submit.innerHTML = defaultSubmitHtml;
            }
        });

        try {
            const response = await fetch('/api/suppliers', { headers: { Accept: 'application/json' } });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const suppliers = await response.json();
            select.replaceChildren();

            const placeholder = document.createElement('option');
            placeholder.value = '';
            placeholder.textContent = suppliers.length ? 'Выберите поставщика' : 'Поставщиков пока нет';
            select.appendChild(placeholder);

            suppliers.forEach(supplier => {
                const option = document.createElement('option');
                option.value = supplier.id;
                option.textContent = supplier.bin_iin ? `${supplier.name} · ${supplier.bin_iin}` : supplier.name;
                select.appendChild(option);
            });

            suppliersReady = suppliers.length > 0;
            select.disabled = !suppliersReady;

            if (!suppliersReady) {
                setHint('Сначала <a href="/suppliers">добавьте поставщика</a>, затем оформляйте приход.', true);
            }
        } catch (error) {
            console.error('SUPPLIERS LOAD ERROR:', error);
            suppliersLoadError = true;
            select.innerHTML = '<option value="">Не удалось загрузить поставщиков</option>';
            select.disabled = true;
            setHint('Не удалось загрузить поставщиков. Обновите страницу или откройте раздел «Поставщики».', true);
        }
    });
})();
