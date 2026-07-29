(function () {
    document.addEventListener('DOMContentLoaded', function () {
        var input = document.getElementById('catalogSearch');
        if (input) input.addEventListener('input', filterCatalogItems);
    });

    var categorySelect = document.getElementById('itemCategoryId');
    if (categorySelect) {
        categorySelect.addEventListener('change', syncCategoryName);
    }

    var retailPriceInput = document.getElementById('itemRetailPrice');
    var purchasePriceInput = document.getElementById('itemPurchasePrice');

    if (retailPriceInput) {
        retailPriceInput.addEventListener('input', function () {
            priceCalculationSource = 'retail';
            calculatePurchasePrice();
        });
    }

    if (purchasePriceInput) {
        purchasePriceInput.addEventListener('input', function () {
            priceCalculationSource = 'purchase';
            calculateRetailPrice();
        });
    }

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') closeItemModal();
    });
})();

document.addEventListener('DOMContentLoaded', function () {
    mountItemModalToBody();
    mountCategoryManagerToBody();
    filterItemCategoryOptions('product');

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') closeItemModal();
    });
});

var activeCatalogTypeFilter = "all";

function setCatalogTypeFilter(type, button) {
    activeCatalogTypeFilter = type || "all";
    document.querySelectorAll(".catalog-type-tab").forEach(function(tab) {
        tab.classList.toggle("is-active", tab === button);
    });
    filterCatalogItems();
}

function filterCatalogItems() {
    var search = document.getElementById('catalogSearch');
    var category = document.getElementById('catalogCategoryFilter');
    var query = search ? search.value.trim().toLowerCase() : '';
    var selectedCategory = category ? category.value.toLowerCase() : 'all';
    var rows = document.querySelectorAll('.catalog-item');
    var visible = 0;

    rows.forEach(function (row) {
        var matchesSearch = !query || (row.dataset.search || '').includes(query);
        var matchesCategory = selectedCategory === 'all' || (row.dataset.category || '') === selectedCategory;
        var matchesType = activeCatalogTypeFilter === 'all' || (row.dataset.itemType || 'product') === activeCatalogTypeFilter;
        var show = matchesSearch && matchesCategory && matchesType;
        row.style.display = show ? '' : 'none';
        if (show) visible += 1;
    });

    var empty = document.getElementById('catalogNoResults');
    if (empty) empty.style.display = visible === 0 ? 'grid' : 'none';
}

function getSelectedCategoryMarkup() {
    var select = document.getElementById('itemCategoryId');
    if (!select || select.selectedIndex < 0) return 0;

    var option = select.options[select.selectedIndex];
    return parseFloat(option.dataset.markup || '0') || 0;
}

var priceCalculationSource = 'purchase';
var suppressPriceCalculation = false;

function roundPrice(value) {
    // В обе стороны всегда округляем вверх до целого тенге.
    return Math.ceil(Number(value) || 0);
}

function calculatePurchasePrice() {
    if (suppressPriceCalculation) return;

    var selectedType = document.querySelector('input[name="item_type"]:checked');
    if (selectedType && selectedType.value === 'service') return;

    var retailField = document.getElementById('itemRetailPrice');
    var purchaseField = document.getElementById('itemPurchasePrice');
    if (!retailField || !purchaseField) return;

    var retail = parseFloat(retailField.value) || 0;
    var markup = getSelectedCategoryMarkup();

    if (retail <= 0) {
        purchaseField.value = '';
        return;
    }

    var divisor = 1 + (markup / 100);
    var purchase = divisor > 0 ? retail / divisor : retail;
    purchaseField.value = roundPrice(purchase);
}

function calculateRetailPrice() {
    if (suppressPriceCalculation) return;

    var selectedType = document.querySelector('input[name="item_type"]:checked');
    if (selectedType && selectedType.value === 'service') return;

    var retailField = document.getElementById('itemRetailPrice');
    var purchaseField = document.getElementById('itemPurchasePrice');
    if (!retailField || !purchaseField) return;

    var purchase = parseFloat(purchaseField.value) || 0;
    var markup = getSelectedCategoryMarkup();

    if (purchase <= 0) {
        retailField.value = '';
        return;
    }

    var retail = purchase * (1 + markup / 100);
    retailField.value = roundPrice(retail);
}

function recalculatePricesByLastSource() {
    if (priceCalculationSource === 'retail') {
        calculatePurchasePrice();
    } else {
        calculateRetailPrice();
    }
}

function syncCategoryName(skipPriceCalculation) {
    var select = document.getElementById('itemCategoryId');
    var hidden = document.getElementById('itemCategory');
    if (!select || !hidden) return;

    hidden.value = select.options[select.selectedIndex]
        ? select.options[select.selectedIndex].text
        : '';

    if (!skipPriceCalculation) recalculatePricesByLastSource();
}


function mountItemModalToBody() {
    var modal = document.getElementById('itemModal');
    if (!modal) return null;

    if (modal.parentElement !== document.body) {
        document.body.appendChild(modal);
    }

    return modal;
}

function openItemModal() {
    var modal = mountItemModalToBody();
    if (!modal) return;
    modal.classList.add('is-open');
    modal.setAttribute('aria-hidden', 'false');
    document.body.classList.add('catalog-modal-open');
    setTimeout(function () { document.getElementById('itemBarcode').focus(); }, 50);
}

function closeItemModal() {
    var modal = mountItemModalToBody();
    if (!modal) return;
    modal.classList.remove('is-open');
    modal.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('catalog-modal-open');
}

function filterItemCategoryOptions(type) {
    type = type === "service" ? "service" : "product";
    var select = document.getElementById("itemCategoryId");
    if (!select) return;

    var currentValue = select.value;
    var currentVisible = false;

    Array.from(select.options).forEach(function(option, index) {
        if (index === 0 || !option.dataset.categoryType) {
            option.hidden = false;
            option.disabled = false;
            return;
        }

        var visible = option.dataset.categoryType === type;
        option.hidden = !visible;
        option.disabled = !visible;

        if (visible && option.value === currentValue) {
            currentVisible = true;
        }
    });

    if (!currentVisible) {
        select.value = "";
    }

    syncCategoryName(true);
}

function applyItemType(type) {
    type = type === "service" ? "service" : "product";
    var modal = document.getElementById("itemModal");
    var productRadio = document.getElementById("itemTypeProduct");
    var serviceRadio = document.getElementById("itemTypeService");
    var subtitle = document.getElementById("itemModalSubtitle");
    var nameLabel = document.getElementById("itemNameLabel");
    var nameInput = document.getElementById("itemName");
    var purchaseLabel = document.getElementById("itemPurchasePriceLabel");
    var retailLabel = document.getElementById("itemRetailPriceLabel");
    var submitButton = document.getElementById("itemSubmitButton");
    if (productRadio) productRadio.checked = type === "product";
    if (serviceRadio) serviceRadio.checked = type === "service";
    if (modal) modal.classList.toggle("is-service", type === "service");
    filterItemCategoryOptions(type);

    var unitSelect = document.getElementById("itemUnit");
    if (unitSelect) {
        if (type === "service" && unitSelect.value === "шт") unitSelect.value = "услуга";
        if (type === "product" && unitSelect.value === "услуга") unitSelect.value = "шт";
    }

    if (nameLabel) nameLabel.textContent = type === "service" ? "Наименование услуги *" : "Название товара *";
    if (nameInput) nameInput.placeholder = type === "service" ? "Например: Установка кассы" : "Например: Молоко 3,2%";
    var descriptionLabel = document.getElementById("itemDescriptionLabel");
    var descriptionInput = document.getElementById("itemDescription");
    var descriptionHint = document.getElementById("itemDescriptionHint");
    if (descriptionLabel) descriptionLabel.textContent = type === "service" ? "Описание услуги" : "Описание товара";
    if (descriptionInput) {
        descriptionInput.placeholder = type === "service"
            ? "Расскажите, что входит в услугу, что получит клиент и какие данные потребуются"
            : "Кратко опишите товар: характеристики, комплектность, назначение или важные особенности";
    }
    if (descriptionHint) {
        descriptionHint.textContent = type === "service"
            ? "Описание будет показано клиенту в карточке услуги на онлайн-витрине."
            : "Описание будет показано клиенту в карточке товара на онлайн-витрине.";
    }
    if (purchaseLabel) purchaseLabel.textContent = type === "service" ? "Закупочная стоимость, ₸" : "Закупочная цена, ₸";
    if (retailLabel) retailLabel.textContent = type === "service" ? "Цена услуги, ₸ *" : "Розничная цена, ₸ *";
    if (subtitle) subtitle.textContent = type === "service" ? "Основные данные услуги, цена и штрихкод" : "Основные данные товара и идентификаторы маркировки";
    if (submitButton) submitButton.textContent = type === "service" ? "Сохранить услугу" : "Сохранить товар";

    var barcodeButton = document.getElementById("barcodeSearchButton");
    if (barcodeButton) {
        barcodeButton.textContent = type === "service" ? "Найти услугу" : "Найти товар";
    }

    if (type === "service") {
        var marked = document.getElementById("itemIsMarked");
        if (marked) marked.checked = false;

        var purchaseField = document.getElementById("itemPurchasePrice");
        if (purchaseField && !purchaseField.value) purchaseField.value = "0";

        updateMarkedBadge();
        clearBarcodeStatus();
    }
}

function setServiceSaleMode(mode){
    mode=['order','booking','request'].includes(mode)?mode:'order';
    var el=document.querySelector('input[name="service_sale_mode"][value="'+mode+'"]');
    if(el) el.checked=true;
}

function openAddItemModal() {
    var form = document.getElementById('itemForm');
    form.reset();
    form.action = '/items/add';
    document.getElementById('itemModalTitle').textContent = 'Новая позиция';
    document.getElementById('itemUnit').value = 'шт';
    applyItemType('product');
    setServiceSaleMode('order');
    document.getElementById('itemIsMarked').checked = false;
    updateMarkedBadge();
    clearBarcodeStatus();
    priceCalculationSource = 'purchase';
    syncCategoryName(true);
    openItemModal();
}

function setValue(id, value) {
    var field = document.getElementById(id);
    if (field) field.value = value === null || value === undefined ? '' : value;
}

function selectItemCategory(value, name) {
    var select = document.getElementById('itemCategoryId');
    if (!select) return;

    var wantedValue = value === null || value === undefined ? '' : String(value);
    var wantedName = name === null || name === undefined ? '' : String(name).trim().toLowerCase();
    var matched = false;

    Array.from(select.options).forEach(function (option) {
        if (matched) return;
        var optionValue = String(option.value);
        var optionName = option.textContent.trim().toLowerCase();
        if ((wantedValue && optionValue === wantedValue) || (wantedName && optionName === wantedName)) {
            select.value = option.value;
            matched = true;
        }
    });

    if (!matched) select.value = '';
}

var barcodeLookupController = null;

function clearBarcodeStatus() {
    var status = document.getElementById('barcodeLookupStatus');
    if (!status) return;
    status.className = 'catalog-barcode-status';
    status.textContent = '';
}

function showBarcodeStatus(type, message) {
    var status = document.getElementById('barcodeLookupStatus');
    if (!status) return;
    status.className = 'catalog-barcode-status is-visible is-' + type;
    status.textContent = message;
}

function updateMarkedBadge() {
    var checkbox = document.getElementById('itemIsMarked');
    var badge = document.getElementById('itemMarkedBadge');
    if (!checkbox || !badge) return;
    badge.textContent = checkbox.checked ? 'Маркированный товар' : 'Обычный товар';
    badge.classList.toggle('is-marked', checkbox.checked);
}

function normalizeMeasure(measure) {
    var value = String(measure || '')
        .trim()
        .toLowerCase()
        .replace(/ё/g, 'е')
        .replace(/\s+/g, ' ');

    var aliases = {
        'штука':'шт','штуки':'шт','штук':'шт','шт.':'шт','piece':'шт','pcs':'шт',
        'пара':'пар','пары':'пар','пар.':'пар','pair':'пар',
        'комплект':'компл','комплекта':'компл','компл.':'компл','к-т':'компл','kit':'компл','set':'компл',
        'набор':'набор',
        'упаковка':'упак','упаковки':'упак','упак.':'упак','уп.':'упак','pack':'упак',
        'пачка':'пач','пач.':'пач',
        'коробка':'кор','кор.':'кор','короб':'кор','box':'кор',
        'бутылка':'бут','бут.':'бут',
        'канистра':'кан','кан.':'кан',
        'рулон':'рул','рул.':'рул','roll':'рул',
        'килограмм':'кг','килограммы':'кг','кг.':'кг','kg':'кг',
        'грамм':'г','граммы':'г','гр':'г','гр.':'г','g':'г','gr':'г',
        'тонна':'т','тонны':'т','т.':'т','ton':'т',
        'литр':'л','литры':'л','л.':'л','liter':'л','litre':'л','l':'л',
        'миллилитр':'мл','миллилитры':'мл','мл.':'мл','ml':'мл',
        'метр':'м','метры':'м','м.':'м','пог.м':'м','пог. м':'м','погонный метр':'м','meter':'м',
        'сантиметр':'см','сантиметры':'см','см.':'см','cm':'см',
        'миллиметр':'мм','миллиметры':'мм','мм.':'мм','mm':'мм',
        'квадратный метр':'м²','кв.м':'м²','кв. м':'м²','м2':'м²','m2':'м²','m²':'м²',
        'кубический метр':'м³','куб.м':'м³','куб. м':'м³','м3':'м³','m3':'м³','m³':'м³',
        'час':'час','часа':'час','часов':'час','ч.':'час','hour':'час',
        'день':'день','дня':'день','дней':'день','сутки':'день','day':'день',
        'неделя':'неделя','недели':'неделя','недель':'неделя','нед.':'неделя','week':'неделя',
        'месяц':'месяц','месяца':'месяц','месяцев':'месяц','мес':'месяц','мес.':'месяц','month':'месяц',
        'год':'год','года':'год','лет':'год','year':'год',
        'смена':'смена','смены':'смена',
        'услуга':'услуга','услуги':'услуга','работа':'услуга','service':'услуга',
        'человек':'человек','чел':'человек','чел.':'человек','person':'человек',
        'место':'место','места':'место','мест':'место',
        'пассажир':'пассажир','пассажира':'пассажир',
        'рейс':'рейс','рейса':'рейс',
        'тур':'тур','тура':'тур'
    };

    return aliases[value] || value;
}

function setUnitFromCatalog(measure) {
    var select = document.getElementById('itemUnit');
    if (!select || !measure) return;
    var normalized = normalizeMeasure(measure);
    var option = Array.from(select.options).find(function (item) {
        return item.value.toLowerCase() === normalized || item.textContent.trim().toLowerCase() === normalized;
    });
    if (option) select.value = option.value;
}

async function lookupBarcode(force) {
    var barcodeField = document.getElementById('itemBarcode');
    var button = document.getElementById('barcodeSearchButton');
    if (!barcodeField) return;

    var barcode = barcodeField.value.trim();
    if (!barcode) {
        if (force) showBarcodeStatus('warning', 'Введите или отсканируйте штрихкод.');
        return;
    }

    if (barcodeLookupController) barcodeLookupController.abort();
    barcodeLookupController = new AbortController();

    var selectedType = document.querySelector('input[name="item_type"]:checked');
    var itemType = selectedType ? selectedType.value : 'product';

    showBarcodeStatus(
        'loading',
        itemType === 'service'
            ? 'Ищем услугу в локальной базе…'
            : 'Ищем товар в базе и Национальном каталоге…'
    );

    if (button) { button.disabled = true; button.textContent = 'Поиск…'; }

    try {
        var response = await fetch(
            '/api/barcode-info/' + encodeURIComponent(barcode) +
            '?item_type=' + encodeURIComponent(itemType),
            {
                headers: { 'Accept': 'application/json' },
                signal: barcodeLookupController.signal
            }
        );
        if (!response.ok) throw new Error('HTTP ' + response.status);
        var data = await response.json();

        if (!data.found) {
            showBarcodeStatus(
                'warning',
                itemType === 'service'
                    ? 'Услуга не найдена. Заполните данные вручную.'
                    : 'Товар не найден. Заполните данные вручную.'
            );
            document.getElementById('itemName').focus();
            return;
        }

        if (data.name) setValue('itemName', data.name);
        if (data.gtin) setValue('itemGtin', data.gtin);
        if (data.ntin) setValue('itemNtin', data.ntin);
        if (data.measure) setUnitFromCatalog(data.measure);
        if (typeof data.is_marked !== 'undefined' && data.is_marked !== null) {
            document.getElementById('itemIsMarked').checked = Boolean(data.is_marked);
            updateMarkedBadge();
        }
        if (data.category) selectItemCategory('', data.category);
        syncCategoryName();

        var source = data.local ? 'локальной базе' : 'Национальном каталоге';
        showBarcodeStatus(
            'success',
            (itemType === 'service' ? 'Услуга' : 'Товар') +
            ' найдена в ' + source + '. Данные заполнены автоматически.'
        );

        if (data.local && data.price && !document.getElementById('itemRetailPrice').value) {
            setValue('itemRetailPrice', data.price);
        }
        document.getElementById('itemRetailPrice').focus();
    } catch (error) {
        if (error.name !== 'AbortError') {
            showBarcodeStatus('error', 'Не удалось выполнить поиск. Проверьте соединение и попробуйте снова.');
        }
    } finally {
        if (button) {
            button.disabled = false;
            button.textContent = itemType === 'service' ? 'Найти услугу' : 'Найти товар';
        }
    }
}

document.addEventListener('DOMContentLoaded', function () {
    var barcodeField = document.getElementById('itemBarcode');
    if (!barcodeField) return;

    barcodeField.addEventListener('keydown', function (event) {
        if (event.key === 'Enter') {
            event.preventDefault();
            lookupBarcode(true);
        }
    });

    barcodeField.addEventListener('input', function () {
        clearBarcodeStatus();
    });
});

function openEditItemModal(item) {
    var form = document.getElementById('itemForm');
    form.reset();
    form.action = '/items/' + encodeURIComponent(item.id) + '/edit';
    document.getElementById('itemModalTitle').textContent = item.item_type === 'service' ? 'Редактировать услугу' : 'Редактировать товар';
    applyItemType(item.item_type || 'product');
    setServiceSaleMode(item.service_sale_mode || 'order');

    setValue('itemName', item.name);
    setValue('itemDescription', item.description || '');
    setValue('itemBarcode', item.barcode);
    setValue('itemGtin', item.gtin);
    setValue('itemNtin', item.ntin);
    setValue('itemPurchasePrice', item.purchase_price);
    setValue('itemRetailPrice', item.retail_price);
    setValue('itemUnit', item.unit || 'шт');
    document.getElementById('itemIsMarked').checked = Boolean(item.is_marked);
    updateMarkedBadge();
    clearBarcodeStatus();
    selectItemCategory(item.category_id, item.category);
    priceCalculationSource = 'purchase';
    syncCategoryName(true);

    openItemModal();
}

function mountCategoryManagerToBody(){
    var modal=document.getElementById('categoryManager');
    if(modal && modal.parentElement!==document.body) document.body.appendChild(modal);
    return modal;
}
var activeCategoryManagerType = "product";

function mountCategoryManagerToBody(){
    var modal=document.getElementById('categoryManager');
    if(modal && modal.parentElement!==document.body) document.body.appendChild(modal);
    return modal;
}

function setCategoryManagerType(type, button){
    activeCategoryManagerType = type === "service" ? "service" : "product";

    document.querySelectorAll('.category-manager__type-tab').forEach(function(tab){
        tab.classList.toggle('is-active', tab.dataset.categoryType === activeCategoryManagerType);
    });

    document.querySelectorAll('#categoryManagerList .category-manager__item').forEach(function(row){
        row.hidden = (row.dataset.categoryType || 'product') !== activeCategoryManagerType;
    });

    var input=document.getElementById('categoryNameInput');
    if(input){
        input.placeholder = activeCategoryManagerType === 'service'
            ? 'Название категории услуги'
            : 'Название категории товара';
    }

    var markupInput=document.getElementById('categoryMarkupInput');
    if(markupInput){
        markupInput.style.display = activeCategoryManagerType === 'service' ? 'none' : '';
        markupInput.disabled = activeCategoryManagerType === 'service';
        if(activeCategoryManagerType === 'service') markupInput.value = '0';
    }

    resetCategoryEditor(false);
}

function openCategoryManager(){
    var selectedType=document.querySelector('input[name="item_type"]:checked');
    var type=selectedType ? selectedType.value : 'product';
    var button=document.querySelector('.category-manager__type-tab[data-category-type="'+type+'"]');

    setCategoryManagerType(type, button);

    var modal=mountCategoryManagerToBody();
    if(modal){
        modal.classList.add('is-open');
        modal.setAttribute('aria-hidden','false');
        document.body.classList.add('catalog-modal-open');
        setTimeout(function(){document.getElementById('categoryNameInput').focus();},50);
    }
}

function closeCategoryManager(){
    var modal=mountCategoryManagerToBody();
    if(modal){
        modal.classList.remove('is-open');
        modal.setAttribute('aria-hidden','true');
        document.body.classList.remove('catalog-modal-open');
    }
    resetCategoryEditor();
}

function resetCategoryEditor(resetTitle){
    setValue('editingCategoryId','');
    setValue('categoryNameInput','');
    setValue('categoryMarkupInput','0');

    var markupInput=document.getElementById('categoryMarkupInput');
    if(markupInput){
        markupInput.style.display = activeCategoryManagerType === 'service' ? 'none' : '';
        markupInput.disabled = activeCategoryManagerType === 'service';
    }

    var button=document.getElementById('saveCategoryButton');
    if(button) button.textContent='Добавить';

    if(resetTitle !== false){
        var title=document.getElementById('categoryManagerTitle');
        if(title) title.textContent='Категории';
    }
}

function startEditCategory(row){
    activeCategoryManagerType = row.dataset.categoryType || 'product';
    setCategoryManagerType(
        activeCategoryManagerType,
        document.querySelector('.category-manager__type-tab[data-category-type="'+activeCategoryManagerType+'"]')
    );

    setValue('editingCategoryId',row.dataset.id);
    setValue('categoryNameInput',row.dataset.name);
    setValue(
        'categoryMarkupInput',
        activeCategoryManagerType === 'product' ? (row.dataset.markup || '0') : '0'
    );

    document.getElementById('saveCategoryButton').textContent='Сохранить';
    document.getElementById('categoryManagerTitle').textContent=
        activeCategoryManagerType === 'service'
            ? 'Редактирование категории услуг'
            : 'Редактирование категории товаров';

    document.getElementById('categoryNameInput').focus();
}

function escapeHtml(value){
    var d=document.createElement('div');
    d.textContent=value;
    return d.innerHTML;
}

function upsertCategoryOption(category, oldName){
    var select=document.getElementById('itemCategoryId');
    var option=Array.from(select.options).find(function(o){
        return String(o.dataset.id||'')===String(category.id);
    });

    if(!option){
        option=document.createElement('option');
        select.appendChild(option);
    }

    option.value=category.id;
    option.dataset.id=category.id;
    option.dataset.categoryType=category.category_type || activeCategoryManagerType;
    option.dataset.markup=category.markup_percent || 0;
    option.textContent=category.name;

    filterItemCategoryOptions(
        document.querySelector('input[name="item_type"]:checked')?.value || 'product'
    );

    if(
        option.dataset.categoryType ===
        (document.querySelector('input[name="item_type"]:checked')?.value || 'product')
    ){
        if(!oldName || document.getElementById('itemCategory').value===oldName){
            select.value=String(category.id);
            syncCategoryName(true);
        }
    }
}

function upsertCategoryRow(category){
    var list=document.getElementById('categoryManagerList');
    var row=list.querySelector('[data-id="'+CSS.escape(String(category.id))+'"]');

    if(!row){
        row=document.createElement('div');
        row.className='category-manager__item';
        list.appendChild(row);
    }

    var type=category.category_type || activeCategoryManagerType;

    row.dataset.id=category.id;
    row.dataset.name=category.name;
    row.dataset.categoryType=type;
    row.dataset.markup=category.markup_percent || 0;
    row.hidden=type!==activeCategoryManagerType;

    row.innerHTML=
        '<div class="category-manager__meta">'+
            '<b>'+escapeHtml(category.name)+'</b>'+
            '<small>'+(type==='service'
                ? 'Категория услуг'
                : 'Наценка: '+escapeHtml(String(category.markup_percent || 0))+'%')+'</small>'+
        '</div>'+
        '<div class="category-manager__actions">'+
            `<button type="button" onclick="startEditCategory(this.closest('.category-manager__item'))" title="Редактировать"><img src="/static/icons/edit.png" class="catalog-action-icon" alt=""></button>`+
            `<button type="button" class="delete" onclick="removeCategory(this.closest('.category-manager__item'))" title="Удалить"><img src="/static/icons/delete-item.png" class="catalog-action-icon" alt=""></button>`+
        '</div>';
}

async function saveCategory(){
    var id=document.getElementById('editingCategoryId').value;
    var name=document.getElementById('categoryNameInput').value.trim();
    var markupInput=document.getElementById('categoryMarkupInput');
    var markup=activeCategoryManagerType === 'product'
        ? parseFloat(markupInput ? markupInput.value : 0) || 0
        : 0;

    if(!name){
        alert('Введите название категории');
        return;
    }

    var button=document.getElementById('saveCategoryButton');
    button.disabled=true;

    try{
        var url=id?'/edit_category/'+encodeURIComponent(id):'/add_category';
        var response=await fetch(url,{
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({
                name:name,
                markup:markup,
                category_type:activeCategoryManagerType
            })
        });

        var data=await response.json();
        if(!response.ok) throw new Error(data.error||'Ошибка сохранения');

        var category={
            id:data.id||id,
            name:data.name||name,
            markup_percent:data.markup_percent ?? markup,
            category_type:data.category_type||activeCategoryManagerType
        };

        var oldRow=id
            ? document.querySelector('#categoryManagerList [data-id="'+CSS.escape(String(id))+'"]')
            : null;
        var oldName=oldRow?oldRow.dataset.name:'';

        upsertCategoryOption(category,oldName);
        upsertCategoryRow(category);
        resetCategoryEditor();
    }catch(e){
        alert(e.message||'Не удалось сохранить категорию');
    }finally{
        button.disabled=false;
    }
}

async function removeCategory(row){
    if(!confirm('Удалить категорию «'+row.dataset.name+'»?')) return;

    var id=row.dataset.id;

    try{
        var response=await fetch('/delete_category/'+encodeURIComponent(id),{method:'POST'});
        var data=await response.json();

        if(!response.ok || data.success===false){
            throw new Error('Не удалось удалить категорию');
        }

        var select=document.getElementById('itemCategoryId');
        var option=Array.from(select.options).find(function(o){
            return String(o.dataset.id||'')===String(id);
        });

        if(option){
            var wasSelected=select.value===option.value;
            option.remove();

            if(wasSelected){
                select.value='';
                syncCategoryName(true);
            }
        }

        row.remove();
        resetCategoryEditor();
    }catch(e){
        alert(e.message||'Не удалось удалить категорию');
    }
}

function mountNikaDataModal(id) {
    const modal = document.getElementById(id);
    if (modal && modal.parentElement !== document.body) document.body.appendChild(modal);
    return modal;
}
function openCatalogDataModal() {
    const modal = mountNikaDataModal('catalogDataModal');
    if (!modal) return;
    modal.classList.add('is-open');
    modal.setAttribute('aria-hidden', 'false');
    document.body.classList.add('nika-data-modal-open');
}
function closeCatalogDataModal() {
    const modal = document.getElementById('catalogDataModal');
    if (!modal) return;
    modal.classList.remove('is-open');
    modal.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('nika-data-modal-open');
}
function openClientsDataModal() {
    const modal = mountNikaDataModal('clientsDataModal');
    if (!modal) return;
    modal.classList.add('is-open');
    modal.setAttribute('aria-hidden', 'false');
    document.body.classList.add('nika-data-modal-open');
}
function closeClientsDataModal() {
    const modal = document.getElementById('clientsDataModal');
    if (!modal) return;
    modal.classList.remove('is-open');
    modal.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('nika-data-modal-open');
}
function updateCatalogDataFile(input) {
    updateNikaDataFileName(input, 'catalogDataFileName');
}
function updateClientsDataFile(input) {
    updateNikaDataFileName(input, 'clientsDataFileName');
}
function updateNikaDataFileName(input, labelId) {
    const label = document.getElementById(labelId);
    const file = input && input.files ? input.files[0] : null;
    if (!label) return;
    label.textContent = file ? file.name : 'Выберите Excel-файл';
}
function showNikaDataResult(resultId, type, message) {
    const result = document.getElementById(resultId);
    if (!result) return;
    result.className = 'nika-data-result ' + (type === 'success' ? 'is-success' : 'is-error');
    result.innerHTML = message;
}
async function submitNikaDataImport(formId, url, resultId) {
    const form = document.getElementById(formId);
    if (!form) return;
    const input = form.querySelector('input[type="file"]');
    const file = input && input.files ? input.files[0] : null;
    if (!file) {
        showNikaDataResult(resultId, 'error', 'Сначала выберите Excel-файл.');
        return;
    }
    if (!file.name.toLowerCase().endsWith('.xlsx')) {
        showNikaDataResult(resultId, 'error', 'Поддерживается только файл формата .xlsx');
        return;
    }

    const submit = form.querySelector('button[type="submit"]');
    submit.disabled = true;
    submit.textContent = 'Импортируем…';
    const result = document.getElementById(resultId);
    if (result) {
        result.className = 'nika-data-result';
        result.textContent = '';
    }

    try {
        const response = await fetch(url, { method: 'POST', body: new FormData(form) });
        const raw = await response.text();
        let data;
        try { data = raw ? JSON.parse(raw) : {}; }
        catch (_) { throw new Error(raw || 'Сервер вернул некорректный ответ'); }

        if (!response.ok || !data.success) {
            throw new Error(data.message || data.error || 'Ошибка импорта');
        }

        const errors = Array.isArray(data.errors) ? data.errors : [];
        let html = `Создано: <b>${data.created || 0}</b><br>` +
                   `Обновлено: <b>${data.updated || 0}</b><br>` +
                   `Пропущено: <b>${data.skipped || 0}</b><br>` +
                   `Ошибок: <b>${errors.length}</b>`;
        if (errors.length) {
            const errorLines = errors.slice(0, 8).map(function(error) {
                if (typeof error === 'string') return error;
                const row = error && error.row ? `Строка ${error.row}: ` : '';
                const message = error && error.message ? error.message : JSON.stringify(error);
                return row + message;
            });
            html += `<br><br><b>Причины:</b><br><small>${errorLines.join('<br>')}</small>`;
        }
        showNikaDataResult(resultId, 'success', html);
        if (!errors.length) setTimeout(() => window.location.reload(), 1100);
    } catch (error) {
        showNikaDataResult(resultId, 'error', error.message || 'Не удалось выполнить импорт');
    } finally {
        submit.disabled = false;
        submit.textContent = 'Начать импорт';
    }
}
function attachNikaDropzone(zone) {
    const input = zone.querySelector('input[type="file"]');
    if (!input) return;

    ['dragenter', 'dragover'].forEach(type => zone.addEventListener(type, event => {
        event.preventDefault();
        event.stopPropagation();
        zone.classList.add('is-dragover');
    }));
    ['dragleave', 'drop'].forEach(type => zone.addEventListener(type, event => {
        event.preventDefault();
        event.stopPropagation();
        zone.classList.remove('is-dragover');
    }));
    zone.addEventListener('drop', event => {
        const files = event.dataTransfer && event.dataTransfer.files;
        if (!files || !files.length) return;
        try {
            const transfer = new DataTransfer();
            transfer.items.add(files[0]);
            input.files = transfer.files;
        } catch (_) {
            try { input.files = files; } catch (__){ return; }
        }
        input.dispatchEvent(new Event('change', { bubbles: true }));
    });
}
document.addEventListener('DOMContentLoaded', () => {
    mountNikaDataModal('catalogDataModal');
    mountNikaDataModal('clientsDataModal');

    const catalogInput = document.getElementById('catalogDataFileInput');
    if (catalogInput) catalogInput.addEventListener('change', () => updateCatalogDataFile(catalogInput));
    const clientsInput = document.getElementById('clientsDataFileInput');
    if (clientsInput) clientsInput.addEventListener('change', () => updateClientsDataFile(clientsInput));

    document.getElementById('catalogDataImportForm')?.addEventListener('submit', event => {
        event.preventDefault();
        submitNikaDataImport('catalogDataImportForm', '/items/import', 'catalogDataImportResult');
    });
    document.getElementById('clientsDataImportForm')?.addEventListener('submit', event => {
        event.preventDefault();
        submitNikaDataImport('clientsDataImportForm', '/clients/import', 'clientsDataImportResult');
    });

    document.querySelectorAll('.nika-data-dropzone').forEach(attachNikaDropzone);
});
document.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
        closeCatalogDataModal();
        closeClientsDataModal();
    }
});
// ================== ОБОГАЩЕНИЕ КАТАЛОГА НКТ ==================
function mountCatalogEnrichmentModal() {
    const modal = document.getElementById('catalogEnrichmentModal');
    if (modal && modal.parentElement !== document.body) document.body.appendChild(modal);
    return modal;
}

function openCatalogEnrichmentModal() {
    closeCatalogDataModal();
    const modal = mountCatalogEnrichmentModal();
    if (!modal) return;
    modal.classList.add('is-open');
    modal.setAttribute('aria-hidden', 'false');
    document.body.classList.add('nika-data-modal-open');
}

function closeCatalogEnrichmentModal() {
    const modal = mountCatalogEnrichmentModal();
    if (!modal) return;
    modal.classList.remove('is-open');
    modal.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('nika-data-modal-open');
}

function getCatalogEnrichmentFields() {
    const fields = {};
    document.querySelectorAll('[data-enrichment-field]').forEach(input => {
        fields[input.dataset.enrichmentField] = Boolean(input.checked);
    });
    return fields;
}

function enrichmentEscape(value) {
    const div = document.createElement('div');
    div.textContent = value == null ? '' : String(value);
    return div.innerHTML;
}

function setEnrichmentProgress(done, total, text) {
    const percent = total ? Math.round(done / total * 100) : 0;
    const bar = document.getElementById('catalogEnrichmentProgressBar');
    const counter = document.getElementById('catalogEnrichmentCounters');
    const label = document.getElementById('catalogEnrichmentProgressText');
    if (bar) bar.style.width = percent + '%';
    if (counter) counter.textContent = done + ' / ' + total;
    if (label) label.textContent = text || 'Поиск товаров…';
}

function renderEnrichmentCandidate(item, candidate) {
    const gtin = candidate.gtin || '—';
    const ntin = candidate.ntin || '—';
    const manufacturer = candidate.manufacturer ? ' · ' + candidate.manufacturer : '';
    return `
        <div class="enrichment-card__candidate">
            <div class="enrichment-card__candidate-info">
                <span class="enrichment-score">Совпадение ${candidate.score || 0}%</span>
                <strong>${enrichmentEscape(candidate.name || 'Без названия')}</strong>
                <span>GTIN: ${enrichmentEscape(gtin)} · NTIN: ${enrichmentEscape(ntin)}${enrichmentEscape(manufacturer)}</span>
            </div>
            <button type="button" class="enrichment-apply">Применить</button>
        </div>`;
}

function appendEnrichmentResult(item, candidates, errorMessage) {
    const root = document.getElementById('catalogEnrichmentResult');
    if (!root) return;

    const card = document.createElement('article');
    card.className = 'enrichment-card';
    card.innerHTML = `
        <div class="enrichment-card__head">
            <div><b>${enrichmentEscape(item.name)}</b><br><small>Текущий штрихкод: ${enrichmentEscape(item.barcode || '—')}</small></div>
        </div>`;

    if (errorMessage) {
        card.innerHTML += `<div class="enrichment-error">${enrichmentEscape(errorMessage)}</div>`;
    } else if (!candidates || !candidates.length) {
        card.innerHTML += '<div class="enrichment-empty">Подходящих карточек НКТ не найдено.</div>';
    } else {
        const candidatesRoot = document.createElement('div');
        candidatesRoot.className = 'enrichment-candidates';
        candidates.forEach(function (candidate) {
            const wrapper = document.createElement('div');
            wrapper.innerHTML = renderEnrichmentCandidate(item, candidate);
            const candidateNode = wrapper.firstElementChild;
            const button = candidateNode.querySelector('.enrichment-apply');
            button.addEventListener('click', async function () {
                button.disabled = true;
                button.textContent = 'Сохраняем…';
                try {
                    const response = await fetch('/api/catalog/enrichment/apply', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
                        body: JSON.stringify({
                            item_id: item.id,
                            candidate: candidate,
                            fields: getCatalogEnrichmentFields()
                        })
                    });
                    const data = await response.json();
                    if (!response.ok || !data.success) throw new Error(data.message || 'Не удалось обновить товар');
                    candidatesRoot.querySelectorAll('.enrichment-apply').forEach(function (otherButton) {
                        otherButton.disabled = true;
                    });
                    button.textContent = 'Применено';
                    button.classList.add('enrichment-applied');
                } catch (error) {
                    button.disabled = false;
                    button.textContent = 'Повторить';
                    alert(error.message || 'Ошибка сохранения');
                }
            });
            candidatesRoot.appendChild(candidateNode);
        });
        card.appendChild(candidatesRoot);
    }
    root.appendChild(card);
}

async function startCatalogEnrichment() {
    const startButton = document.getElementById('catalogEnrichmentStart');
    const settings = document.getElementById('catalogEnrichmentSettings');
    const work = document.getElementById('catalogEnrichmentWork');
    const result = document.getElementById('catalogEnrichmentResult');
    const limit = document.getElementById('catalogEnrichmentLimit')?.value || '25';
    const onlyMissing = document.getElementById('enrichOnlyMissing')?.checked ? '1' : '0';

    if (startButton) {
        startButton.disabled = true;
        startButton.textContent = 'Подготовка…';
    }

    try {
        const listResponse = await fetch(`/api/catalog/enrichment/items?limit=${encodeURIComponent(limit)}&only_missing=${onlyMissing}`, {
            headers: {'Accept': 'application/json'}
        });
        const listData = await listResponse.json();
        if (!listResponse.ok || !listData.success) throw new Error(listData.message || 'Не удалось получить товары');

        const items = Array.isArray(listData.items) ? listData.items : [];
        if (!items.length) {
            throw new Error('Нет товаров, которым требуется обогащение.');
        }

        if (settings) settings.hidden = true;
        if (work) work.hidden = false;
        if (result) result.innerHTML = '';
        setEnrichmentProgress(0, items.length, 'Поиск карточек НКТ…');

        for (let index = 0; index < items.length; index += 1) {
            const item = items[index];
            try {
                const response = await fetch('/api/catalog/enrichment/search', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
                    body: JSON.stringify({item_id: item.id})
                });
                const data = await response.json();
                if (!response.ok || !data.success) {
                    if (data.configured === false) throw new Error(data.message);
                    appendEnrichmentResult(item, [], data.message || 'Ошибка поиска');
                } else {
                    appendEnrichmentResult(item, data.candidates || []);
                }
            } catch (error) {
                appendEnrichmentResult(item, [], error.message || 'Ошибка соединения');
                if ((error.message || '').includes('NCT_API_TOKEN')) {
                    setEnrichmentProgress(index + 1, items.length, 'Нужно добавить ключ НКТ');
                    break;
                }
            }
            setEnrichmentProgress(index + 1, items.length, 'Поиск карточек НКТ…');
        }
        setEnrichmentProgress(items.length, items.length, 'Поиск завершён');
    } catch (error) {
        alert(error.message || 'Не удалось начать обогащение');
        if (settings) settings.hidden = false;
        if (work) work.hidden = true;
    } finally {
        if (startButton) {
            startButton.disabled = false;
            startButton.textContent = 'Начать поиск';
        }
    }
}

document.addEventListener('DOMContentLoaded', mountCatalogEnrichmentModal);
document.addEventListener('keydown', event => {
    if (event.key === 'Escape') closeCatalogEnrichmentModal();
});
