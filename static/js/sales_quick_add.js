(function () {
    if (!window.location.pathname.startsWith('/sales')) return;

    const modal = document.getElementById('addItemModal');
    const categoryInput = document.getElementById('newCategory');
    const categoryDropdown = document.getElementById('quickCategoryDropdown');
    const saveButton = modal?.querySelector('button[onclick="saveNewItem()"]');

    if (!modal || !categoryInput || !categoryDropdown || !saveButton) return;

    let categories = [];
    let selectedMarkup = 0;
    let saving = false;

    function normalizeNumber(value) {
        const normalized = String(value ?? '').trim().replace(/\s+/g, '').replace(',', '.');
        const number = Number(normalized);
        return Number.isFinite(number) ? number : 0;
    }

    function closeDropdown() {
        categoryDropdown.classList.remove('open');
    }

    function renderCategories(filter = '') {
        const query = String(filter || '').trim().toLowerCase();
        const items = categories.filter(item => !query || String(item.name || '').toLowerCase().includes(query));

        if (!items.length) {
            categoryDropdown.innerHTML = '<div class="quick-category-empty">Категории не найдены</div>';
            categoryDropdown.classList.add('open');
            return;
        }

        categoryDropdown.innerHTML = items.map(item => `
            <button type="button" class="quick-category-option" data-name="${String(item.name || '').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}" data-markup="${Number(item.markup_percent || 0)}">
                <span>${String(item.name || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}</span>
                <small>${Number(item.markup_percent || 0)}%</small>
            </button>
        `).join('');
        categoryDropdown.classList.add('open');
    }

    async function loadCategories() {
        try {
            const response = await fetch('/api/categories?type=product', {headers:{Accept:'application/json'}});
            const data = await response.json();
            categories = Array.isArray(data) ? data : [];
            renderCategories(categoryInput.value);
        } catch (error) {
            categories = [];
            categoryDropdown.innerHTML = '<div class="quick-category-empty">Не удалось загрузить категории</div>';
            categoryDropdown.classList.add('open');
        }
    }

    function applyCategory(name, markup) {
        categoryInput.value = name;
        selectedMarkup = Number(markup || 0);
        closeDropdown();

        const retail = normalizeNumber(document.getElementById('newPrice')?.value);
        const purchase = document.getElementById('newPurchasePrice');
        if (purchase && retail > 0 && selectedMarkup > 0 && !purchase.value) {
            purchase.value = Math.round(retail - (retail * selectedMarkup / 100));
        }
    }

    categoryInput.addEventListener('focus', () => {
        if (!categories.length) loadCategories();
        else renderCategories(categoryInput.value);
    });
    categoryInput.addEventListener('input', () => renderCategories(categoryInput.value));
    categoryInput.addEventListener('click', () => {
        if (!categories.length) loadCategories();
        else renderCategories(categoryInput.value);
    });

    categoryDropdown.addEventListener('click', event => {
        const option = event.target.closest('.quick-category-option');
        if (!option) return;
        applyCategory(option.dataset.name || '', option.dataset.markup || 0);
    });

    document.addEventListener('click', event => {
        if (!event.target.closest('.category-wrapper')) closeDropdown();
    });

    window.openAddItemModal = function (code) {
        modal.style.display = 'flex';
        document.getElementById('newBarcode').value = code || '';
        document.getElementById('newName').value = '';
        document.getElementById('newPrice').value = '';
        document.getElementById('newCategory').value = '';
        document.getElementById('newUnit').value = 'шт';
        document.getElementById('newPurchasePrice').value = '';
        selectedMarkup = 0;
        categoryDropdown.innerHTML = '';
        closeDropdown();

        fetch('/api/barcode-info/' + encodeURIComponent(code || ''))
            .then(res => res.json())
            .then(data => {
                if (!data || !data.name) return;
                document.getElementById('newName').value = data.name || '';
                const gtinNode = document.getElementById('newGtin');
                const ntinNode = document.getElementById('newNtin');
                const markedNode = document.getElementById('newIsMarked');
                if (gtinNode) gtinNode.value = data.gtin || '';
                if (ntinNode) ntinNode.value = data.ntin || '';
                if (markedNode) markedNode.checked = Boolean(data.is_marked);
            })
            .catch(() => {});

        setTimeout(() => document.getElementById('newName')?.focus(), 30);
    };

    window.closeAddItemModal = function () {
        closeDropdown();
        modal.style.display = 'none';
    };

    window.saveNewItem = async function () {
        if (saving) return;

        const name = String(document.getElementById('newName')?.value || '').trim();
        const retailPrice = normalizeNumber(document.getElementById('newPrice')?.value);
        const purchasePrice = normalizeNumber(document.getElementById('newPurchasePrice')?.value);
        const barcode = String(document.getElementById('newBarcode')?.value || '').trim();
        const category = String(document.getElementById('newCategory')?.value || '').trim();
        const unit = String(document.getElementById('newUnit')?.value || 'шт').trim();
        const gtin = String(document.getElementById('newGtin')?.value || currentBarcodeData?.gtin || '').trim();
        const ntin = String(document.getElementById('newNtin')?.value || currentBarcodeData?.ntin || '').trim();
        const isMarked = Boolean(document.getElementById('newIsMarked')?.checked || currentBarcodeData?.is_marked);

        if (!name) {
            alert('Укажите название товара');
            document.getElementById('newName')?.focus();
            return;
        }
        if (retailPrice <= 0) {
            alert('Укажите розничную цену');
            document.getElementById('newPrice')?.focus();
            return;
        }
        if (!category) {
            alert('Выберите категорию');
            categoryInput.focus();
            return;
        }

        saving = true;
        saveButton.disabled = true;
        const oldText = saveButton.textContent;
        saveButton.textContent = 'Сохраняем…';

        try {
            const response = await fetch('/api/items/create', {
                method: 'POST',
                headers: {'Content-Type':'application/json', Accept:'application/json'},
                body: JSON.stringify({
                    name,
                    category,
                    unit,
                    item_type: 'product',
                    type: 'piece',
                    retail_price: retailPrice,
                    purchase_price: purchasePrice,
                    wholesale_price: 0,
                    discount_percent: 0,
                    barcode,
                    gtin,
                    ntin,
                    is_marked: isMarked,
                    quantity: 0,
                    description: ''
                })
            });

            let data = {};
            try { data = await response.json(); } catch (e) {}
            if (!response.ok || !data.success || !data.item) {
                throw new Error(data.message || data.error || 'Не удалось сохранить товар');
            }

            const item = data.item;
            window.closeAddItemModal();
            if (typeof selectItemForSale === 'function') {
                selectItemForSale(
                    Number(item.id),
                    item.name || name,
                    Number(item.retail_price || retailPrice),
                    item.unit || unit,
                    item.gtin || gtin,
                    item.ntin || ntin
                );
            } else if (typeof addToCart === 'function') {
                addToCart(Number(item.id), item.name || name, Number(item.retail_price || retailPrice));
            }
        } catch (error) {
            alert(error.message || 'Не удалось сохранить товар');
        } finally {
            saving = false;
            saveButton.disabled = false;
            saveButton.textContent = oldText || 'Сохранить';
        }
    };
})();
