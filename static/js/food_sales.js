(() => {
    const MODE_KEY = "nika_sales_mode";
    const PAGE_SIZE = 36;
    const foodCheckoutMode = ["fast","orders","external"].includes(window.NIKA_FOOD_CHECKOUT_MODE)
        ? window.NIKA_FOOD_CHECKOUT_MODE : "fast";
    let foodItems = [];
    let foodCategory = "all";
    let foodSection = "dishes";
    let foodDrinkCategory = null;
    let foodCategoryRows = [];
    let foodLoaded = false;
    let foodLoading = false;
    let foodHasMore = false;
    let foodPage = 0;
    let foodRequestVersion = 0;
    let foodSearchTimer = null;
    let foodAbortController = null;
    let foodCategoryNames = [];

    function money(value) {
        return Number(value || 0).toLocaleString("ru-RU", {
            minimumFractionDigits: 0,
            maximumFractionDigits: 2
        }) + " ₸";
    }

    function currentMode() {
        const businessMode = window.NIKA_BUSINESS_MODE || "universal";
        if (businessMode === "foodservice") return "food";
        if (businessMode === "retail") return "retail";
        const saved = localStorage.getItem(MODE_KEY);
        return saved === "food" ? "food" : "retail";
    }

    function setMode(mode) {
        const businessMode = window.NIKA_BUSINESS_MODE || "universal";
        const next = businessMode === "foodservice" ? "food" : (businessMode === "retail" ? "retail" : (mode === "food" ? "food" : "retail"));
        if (businessMode === "universal") localStorage.setItem(MODE_KEY, next);

        const retailPanel = document.getElementById("retailSalesPanel");
        const foodPanel = document.getElementById("foodSalesPanel");
        const retailBtn = document.getElementById("salesModeRetail");
        const foodBtn = document.getElementById("salesModeFood");

        if (retailPanel) retailPanel.hidden = next !== "retail";
        if (foodPanel) foodPanel.hidden = next !== "food";
        retailBtn?.classList.toggle("active", next === "retail");
        foodBtn?.classList.toggle("active", next === "food");
        retailBtn?.setAttribute("aria-selected", next === "retail" ? "true" : "false");
        foodBtn?.setAttribute("aria-selected", next === "food" ? "true" : "false");

        document.body.classList.toggle("food-sales-mode", next === "food");
        updateFoodCheckoutControls(next === "food");
        const historyBtn = document.getElementById("historyTabBtn");
        if (historyBtn) {
            historyBtn.textContent = next === "food" ? "История заказов" : "История продаж";
            if (historyBtn.getAttribute("aria-selected") === "true" &&
                typeof switchSalesTab === "function") {
                switchSalesTab("history");
            }
        }

        if (next === "food") {
            loadFoodMenu();
            renderFoodCart();
            window.setTimeout(() => document.getElementById("foodSearch")?.focus(), 40);
        }
    }

    async function loadFoodCategories() {
        try {
            const response = await fetch("/api/catalog/food-categories");
            if (!response.ok) throw new Error("HTTP " + response.status);
            const data = await response.json();
            if (!data.success) throw new Error("Не удалось загрузить категории");
            foodCategoryRows = Array.isArray(data.categories) ? data.categories : [];
            foodCategoryNames = foodCategoryRows.map(row => row.name);
            const drinks = foodCategoryRows.find(row => /напит|drink|beverage/i.test(String(row.name || "")));
            foodDrinkCategory = drinks ? drinks.name : null;
            updateFoodQuickFilters();
            renderFoodCategories();
        } catch (error) {
            console.error("FOOD CATEGORIES ERROR:", error);
        }
    }

    async function loadFoodMenu(reset = false) {
        if (reset) {
            foodRequestVersion++;
            foodAbortController?.abort();
            foodLoading = false;
            foodLoaded = false;
            foodItems = [];
            foodPage = 0;
            foodHasMore = false;
            const grid = document.getElementById("foodMenuGrid");
            if (grid) { grid.scrollTop = 0; grid.scrollLeft = 0; }
        }
        if (foodLoading || (foodLoaded && !reset)) return;
        if (!foodPage) loadFoodCategories();
        await fetchFoodPage();
    }

    async function fetchFoodPage() {
        if (foodLoading || (foodPage > 0 && !foodHasMore)) return;
        const version = ++foodRequestVersion;
        const controller = new AbortController();
        foodAbortController = controller;
        foodLoading = true;
        const grid = document.getElementById("foodMenuGrid");
        if (foodPage === 0 && grid) grid.innerHTML = '<div class="food-menu-loading">Загружаем меню…</div>';
        renderFoodPagination();
        try {
            const params = new URLSearchParams({
                // Preserve global menu search even though dishes are the default.
                type: foodSection === "dishes" && !String(document.getElementById("foodSearch")?.value || "").trim() ? "dish" : "food_menu",
                limit: String(PAGE_SIZE),
                page: String(foodPage + 1)
            });
            const query = String(document.getElementById("foodSearch")?.value || "").trim();
            if (query) params.set("q", query);
            if (foodCategory !== "all") params.set("category", foodCategory);
            const response = await fetch("/api/catalog/items?" + params, { signal: controller.signal });
            if (!response.ok) throw new Error("HTTP " + response.status);
            const data = await response.json();
            if (version !== foodRequestVersion) return;
            const newItems = Array.isArray(data.items) ? data.items : [];
            const append = foodPage > 0;
            foodItems.push(...newItems);
            foodPage++;
            foodHasMore = Boolean(data.has_more);
            foodLoaded = true;
            // Preserve decoded images and scroll position on pagination.
            renderFoodMenu(append, newItems);
        } catch (error) {
            if (error.name === "AbortError" || version !== foodRequestVersion) return;
            console.error("FOOD MENU LOAD ERROR:", error);
            if (grid && foodPage === 0) grid.innerHTML = '<div class="food-menu-empty">Не удалось загрузить каталог. Проверьте соединение и повторите поиск.</div>';
        } finally {
            if (version === foodRequestVersion) {
                foodLoading = false;
                renderFoodPagination();
            }
        }
    }

    function renderFoodPagination() {
        const button = document.getElementById("foodMenuLoadMore");
        if (!button) return;
        button.hidden = !foodHasMore || foodLoading;
        button.disabled = foodLoading;
        button.textContent = foodSection === "dishes" && !String(document.getElementById("foodSearch")?.value || "").trim() ? "Показать ещё блюда" : "Показать ещё позиции";
    }

    function refreshFoodMenu() {
        clearTimeout(foodSearchTimer);
        loadFoodMenu(true);
    }

    function itemCategory(item) {
        return String(item?.category || "").trim() || "Без категории";
    }

    function setFoodCategoryPopover(open) {
        const popover = document.getElementById("foodCategoryPopover");
        const toggle = document.getElementById("foodCategoryToggle");
        if (!popover || !toggle) return;
        popover.hidden = !open;
        toggle.setAttribute("aria-expanded", String(open));
        if (open) {
            const search = document.getElementById("foodCategorySearch");
            if (search) {
                search.value = "";
                filterFoodCategories();
                search.focus();
            }
        }
    }

    function filterFoodCategories() {
        const query = String(document.getElementById("foodCategorySearch")?.value || "").trim().toLocaleLowerCase("ru");
        let visible = 0;
        document.querySelectorAll("#foodCategories .food-category-btn").forEach(button => {
            const matches = button.dataset.category === "all" || button.textContent.toLocaleLowerCase("ru").includes(query);
            button.hidden = !matches;
            if (matches) visible++;
        });
        const empty = document.getElementById("foodCategoryEmpty");
        if (empty) empty.hidden = visible > (query ? 1 : 0);
    }

    function updateFoodQuickFilters() {
        const drinksTab = document.querySelector('[data-food-section="drinks"]');
        if (drinksTab) drinksTab.hidden = !foodDrinkCategory;
        document.querySelectorAll("[data-food-section]").forEach(button => {
            const active = button.dataset.foodSection === foodSection;
            button.classList.toggle("active", active);
            button.setAttribute("aria-pressed", String(active));
        });
        const hint = document.getElementById("foodMenuSectionHint");
        if (hint) hint.textContent = foodSection === "dishes" ? "Основные блюда" : foodSection === "drinks" ? "Напитки" : "Всё меню";
    }

    function selectFoodSection(section) {
        if (section === "drinks" && !foodDrinkCategory) return;
        foodSection = section;
        foodCategory = section === "drinks" ? foodDrinkCategory : "all";
        updateFoodQuickFilters();
        updateCategoryButtons();
        setFoodCategoryPopover(false);
        refreshFoodMenu();
    }

    function renderFoodCategories() {
        const root = document.getElementById("foodCategories");
        if (!root) return;
        const categories = [...foodCategoryRows].sort((a, b) =>
            Number(b.dish_count || 0) - Number(a.dish_count || 0) ||
            String(a.name || "").localeCompare(String(b.name || ""), "ru"));
        root.replaceChildren();
        const count = document.getElementById("foodCategoryCount");
        if (count) count.textContent = String(categories.length);

        const allButton = document.createElement("button");
        allButton.type = "button";
        allButton.className = "food-category-btn";
        allButton.dataset.category = "all";
        allButton.textContent = "Все категории";
        allButton.addEventListener("click", () => selectFoodCategory("all"));
        root.appendChild(allButton);

        categories.forEach(category => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "food-category-btn";
            button.dataset.category = category.name;
            const label = document.createElement("span");
            label.textContent = category.name;
            const amount = document.createElement("small");
            amount.textContent = String(category.count || 0);
            button.append(label, amount);
            button.addEventListener("click", () => selectFoodCategory(category.name));
            root.appendChild(button);
        });
        updateCategoryButtons();
        filterFoodCategories();
    }

    function selectFoodCategory(category) {
        foodCategory = category || "all";
        foodSection = "all";
        updateFoodQuickFilters();
        updateCategoryButtons();
        refreshFoodMenu();
        setFoodCategoryPopover(false);
        document.getElementById("foodCategoryToggle")?.focus();
    }

    function updateCategoryButtons() {
        document.querySelectorAll("#foodCategories .food-category-btn").forEach(button => {
            const active = button.dataset.category === foodCategory;
            button.classList.toggle("active", active);
            button.setAttribute("aria-pressed", String(active));
        });
        const selected = document.getElementById("foodCategorySelected");
        if (selected) selected.textContent = foodCategory === "all" ? "Категории меню" : foodCategory;
    }

    function menuInitial(name) {
        const value = String(name || "").trim();
        return value ? value[0].toUpperCase() : "N";
    }

    let pendingModifierItem = null;
    let pendingModifierGroups = [];
    let pendingRecipeIngredients = [];
    let pendingModifierCartLine = null;
    let foodChoiceRequest = 0;

    async function addFoodItem(item) {
        if ((item.item_type || "product") !== "dish") {
            selectItemForSale(Number(item.id), item.name || "Товар", Number(item.retail_price || 0), item.unit || "шт", item.gtin || "", item.ntin || "");
            renderFoodCart();
            return;
        }
        const requestVersion = ++foodChoiceRequest;
        try {
            const [modifierResponse, recipeResponse] = await Promise.all([
                fetch('/api/items/' + encodeURIComponent(item.id) + '/modifiers', {headers:{Accept:'application/json'}}),
                fetch('/api/items/' + encodeURIComponent(item.id) + '/recipe', {headers:{Accept:'application/json'}})
            ]);
            if (!modifierResponse.ok || !recipeResponse.ok) throw new Error('Не удалось загрузить настройки блюда');
            const modifierData = await modifierResponse.json();
            const recipeData = await recipeResponse.json();
            if (requestVersion !== foodChoiceRequest) return;
            if (!modifierData.success || !recipeData.success) throw new Error('Не удалось загрузить состав блюда');
            if (!Array.isArray(recipeData.ingredients) || !recipeData.ingredients.length) {
                throw new Error('Для этого блюда не заполнена техкарта. Заполните её перед продажей.');
            }
            openFoodModifierModal(item, modifierData.groups || [], recipeData.ingredients);
        } catch (error) {
            if (requestVersion === foodChoiceRequest) alert(error.message || 'Не удалось открыть настройки блюда');
        }
    }


    // Existing order prices already include their selected modifiers.
    function foodCartEditBasePrice(line) {
        const extras = (Array.isArray(line?.modifiers) ? line.modifiers : [])
            .reduce((sum, option) => sum + Number(option.price_delta || 0), 0);
        return Number(line?.price || 0) - extras;
    }

    async function editFoodCartItem(index) {
        if (foodOrderBusy || foodCheckoutBusy || window.nikaKaspiPosActive) {
            foodMessage('Дождитесь завершения текущей операции');
            return;
        }
        if (currentMode() !== 'food') return;
        const line = getCart()[index];
        if (!line || (line.item_type && line.item_type !== 'dish')) return;
        const base = foodCartEditBasePrice(line);
        if (!Number.isFinite(base) || base < 0) {
            foodMessage('Некорректная цена позиции, проверьте заказ');
            return;
        }
        const requestVersion = ++foodChoiceRequest;
        try {
            const [modResponse, recipeResponse] = await Promise.all([
                fetch('/api/items/' + encodeURIComponent(line.id) + '/modifiers', {headers:{Accept:'application/json'}}),
                fetch('/api/items/' + encodeURIComponent(line.id) + '/recipe', {headers:{Accept:'application/json'}})
            ]);
            if (requestVersion !== foodChoiceRequest || !getCart().includes(line)) return;
            if (!modResponse.ok || !recipeResponse.ok) throw new Error('Изменение состава доступно только для блюд');
            const modData = await modResponse.json();
            const recipeData = await recipeResponse.json();
            if (requestVersion !== foodChoiceRequest || !getCart().includes(line)) return;
            if (!modData.success || !recipeData.success) throw new Error('Не удалось загрузить модификаторы');
            if (!Array.isArray(recipeData.ingredients) || !recipeData.ingredients.length) {
                throw new Error('У этого блюда отсутствует техкарта. Заполните её в каталоге.');
            }
            openFoodModifierModal({
                ...line, item_type: 'dish', retail_price: base
            }, modData.groups || [], recipeData.ingredients, line);
        } catch (error) {
            if (requestVersion === foodChoiceRequest) foodMessage(error.message || 'Ошибка открытия модификаторов');
        }
    }

    function setFoodModifierTab(tabName) {
        const selected = tabName === 'remove' ? 'remove' : 'add';
        for (const [name, tabId, paneId] of [
            ['add', 'foodModifierAddTab', 'foodModifierGroups'],
            ['remove', 'foodModifierRemoveTab', 'foodModifierExclusions']
        ]) {
            const tab = document.getElementById(tabId);
            const pane = document.getElementById(paneId);
            const active = selected === name;
            if (tab) {
                tab.setAttribute('aria-selected', String(active));
                tab.classList.toggle('is-active', active);
                tab.tabIndex = active ? 0 : -1;
            }
            if (pane) pane.hidden = !active;
        }
    }

    function updateFoodModifierTabCounts() {
        for (const [paneId, badgeId] of [
            ['foodModifierGroups', 'foodModifierAddCount'],
            ['foodModifierExclusions', 'foodModifierRemoveCount']
        ]) {
            const count = document.querySelectorAll('#' + paneId + ' input:checked').length;
            const badge = document.getElementById(badgeId);
            if (badge) {
                badge.textContent = String(count);
                badge.hidden = count === 0;
            }
        }
    }

    function openFoodModifierModal(item, groups, ingredients, editingLine = null) {
        pendingModifierItem = item;
        pendingModifierGroups = groups;
        pendingRecipeIngredients = ingredients;
        pendingModifierCartLine = editingLine;
        const selectedModifierIds = new Set((editingLine?.modifiers || []).map(option => String(option.id)));
        const selectedExclusions = new Set((editingLine?.excluded_ingredients || []).map(ingredient => String(ingredient.id ?? ingredient.item_id)));
        const modal = document.getElementById('foodModifierModal');
        // Escape the sales-grid stacking context: the checkout is mounted
        // directly under body on phones and otherwise covers this dialog.
        if (modal && modal.parentElement !== document.body) document.body.appendChild(modal);
        document.body.classList.add('food-modifier-open');
        const addRoot = document.getElementById('foodModifierGroups');
        const removeRoot = document.getElementById('foodModifierExclusions');
        document.getElementById('foodModifierTitle').textContent = item.name || 'Блюдо';
        const submit = document.getElementById('foodModifierAdd');
        if (submit) submit.textContent = editingLine ? 'Сохранить изменения' : 'Добавить в заказ';
        addRoot.replaceChildren();
        removeRoot.replaceChildren();

        const addHelp = document.createElement('p');
        addHelp.className = 'food-modifier-pane-help';
        addHelp.textContent = 'Выберите дополнения к блюду. Некоторые из них увеличивают цену.';
        addRoot.appendChild(addHelp);
        const hasOptions = groups.some(group => (group.options || []).length > 0);
        if (!hasOptions) {
            const empty = document.createElement('p');
            empty.className = 'food-modifier-pane-empty';
            empty.textContent = 'Для этого блюда нет доступных дополнений. Перейдите в «Убрать», чтобы изменить состав.';
            addRoot.appendChild(empty);
        }
        groups.forEach(group => {
            const section = document.createElement('section');
            section.className = 'food-modifier-group';
            section.innerHTML = '<div class="food-modifier-group-title"><strong>' + escapeFood(group.name) + '</strong><small>' +
                (group.min_select > 0 ? 'Выберите обязательно' : 'По желанию') +
                (group.max_select > 1 ? ' · до ' + group.max_select : '') + '</small></div>';
            (group.options || []).forEach(option => {
                const label = document.createElement('label');
                label.className = 'food-modifier-option';
                const input = document.createElement('input');
                input.type = 'checkbox';
                input.name = 'food-modifier-' + group.id;
                input.value = option.id;
                input.dataset.groupId = group.id;
                input.checked = selectedModifierIds.has(String(option.id));
                input.addEventListener('change', () => {
                    const checked = section.querySelectorAll('input:checked');
                    const max = Number(group.max_select || 0);
                    if (max > 0 && checked.length > max) { input.checked = false; return; }
                    renderFoodModifierTotal();
                });
                const text = document.createElement('span');
                text.innerHTML = '<b>' + escapeFood(option.name) + '</b>' +
                    (Number(option.price_delta) ? '<small>+' + money(option.price_delta) + '</small>' : '');
                label.append(input, text);
                section.appendChild(label);
            });
            addRoot.appendChild(section);
        });

        const removeHelp = document.createElement('p');
        removeHelp.className = 'food-modifier-pane-help food-modifier-remove-help';
        removeHelp.textContent = 'Отметьте ингредиенты, которые нужно убрать. Цена блюда при этом не меняется.';
        removeRoot.appendChild(removeHelp);
        if (ingredients.length) {
            const section = document.createElement('section');
            section.className = 'food-modifier-group food-exclusions-group';
            ingredients.forEach(ingredient => {
                const label = document.createElement('label');
                label.className = 'food-modifier-option food-exclusion-option';
                const input = document.createElement('input');
                input.type = 'checkbox';
                input.dataset.excludedIngredientId = String(ingredient.item_id);
                input.checked = selectedExclusions.has(String(ingredient.item_id));
                input.addEventListener('change', updateFoodModifierTabCounts);
                const name = document.createElement('span');
                name.textContent = 'Без ' + (ingredient.name || 'ингредиента');
                label.append(input, name);
                section.appendChild(label);
            });
            removeRoot.appendChild(section);
        }
        modal.hidden = false;
        setFoodModifierTab(hasOptions ? 'add' : 'remove');
        renderFoodModifierTotal();
    }
    function escapeFood(v){const d=document.createElement('div');d.textContent=String(v||'');return d.innerHTML;}
    function selectedFoodModifiers(){const selected=[];document.querySelectorAll('#foodModifierGroups input:checked').forEach(input=>{const g=pendingModifierGroups.find(x=>String(x.id)===String(input.dataset.groupId));const o=g?.options?.find(x=>String(x.id)===String(input.value));if(o)selected.push(o)});return selected}
    function renderFoodModifierTotal(){const extra=selectedFoodModifiers().reduce((s,o)=>s+Number(o.price_delta||0),0);const total=Number(pendingModifierItem?.retail_price||0)+extra;const n=document.getElementById('foodModifierTotal');if(n)n.textContent=money(total);updateFoodModifierTabCounts()}
    function closeFoodModifierModal(){const m=document.getElementById('foodModifierModal');if(m)m.hidden=true;document.body.classList.remove('food-modifier-open');pendingModifierItem=null;pendingModifierGroups=[];pendingRecipeIngredients=[];pendingModifierCartLine=null}
    function confirmFoodModifiers(){
        if(!pendingModifierItem)return;
        for(const group of pendingModifierGroups){const count=document.querySelectorAll('#foodModifierGroups input[data-group-id="'+group.id+'"]:checked').length;if(count<Number(group.min_select||0)){setFoodModifierTab('add');alert('Выберите: '+group.name);return}}
        const mods=selectedFoodModifiers(); const price=Number(pendingModifierItem.retail_price||0)+mods.reduce((s,o)=>s+Number(o.price_delta||0),0);
        const excludedIngredients = Array.from(document.querySelectorAll('#foodModifierExclusions input[data-excluded-ingredient-id]:checked')).map(input => {
            const ingredient = pendingRecipeIngredients.find(row => String(row.item_id) === input.dataset.excludedIngredientId);
            return {id:Number(ingredient.item_id),name:ingredient.name};
        });
        const values = {
            price, item_type: 'dish',
            modifiers: mods.map(o => ({id:o.id,name:o.name,price_delta:Number(o.price_delta||0)})),
            excluded_ingredients: excludedIngredients
        };
        if (pendingModifierCartLine) {
            if (!getCart().includes(pendingModifierCartLine)) {
                closeFoodModifierModal();
                foodMessage('Позиция больше не находится в корзине');
                return;
            }
            Object.assign(pendingModifierCartLine, values);
            delete pendingModifierCartLine.line_total;
        } else {
            cart.push({
                id:Number(pendingModifierItem.id),
                name:pendingModifierItem.name||'Блюдо',
                qty:1,gtin:pendingModifierItem.gtin||'',ntin:pendingModifierItem.ntin||'',
                unit:pendingModifierItem.unit||'шт',
                ...values
            });
        }
        currentFoodOrderSaved = false;
        lastFoodPrintFingerprint = null;
        lastFoodPrintUiSignature = null;
        showFoodPrintStatus('');
        closeFoodModifierModal(); renderCart(); renderFoodCart();
    }

    function makeFoodCard(item) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "food-menu-card";
        button.title = item.name || "Без названия";
        button.setAttribute("aria-label", "Добавить в заказ: " + (item.name || "Без названия") + ", " + money(item.retail_price));

        const media = document.createElement("div");
        media.className = "food-menu-image";

        const showImages = window.NIKA_SHOW_CATALOG_IMAGES !== false;
        if (showImages && item.image) {
            const img = document.createElement("img");
            img.alt = "";
            // Lazy decoding on the first wheel movement after a long idle
            // produces visible stalls in nested Electron menu scrollers.
            // Begin loading this small page ahead of the user's scroll.
            img.loading = "eager";
            img.decoding = "async";
            img.fetchPriority = "low";
            img.src = item.image;
            img.addEventListener("error", () => {
                media.innerHTML = "";
                const placeholder = document.createElement("span");
                placeholder.className = "food-menu-placeholder";
                placeholder.textContent = menuInitial(item.name);
                media.appendChild(placeholder);
            }, { once: true });
            media.appendChild(img);
        } else {
            const placeholder = document.createElement("span");
            placeholder.className = "food-menu-placeholder";
            placeholder.textContent = menuInitial(item.name);
            media.appendChild(placeholder);
        }

        const categoryBadge = document.createElement("span");
        categoryBadge.className = "food-menu-category-badge";
        categoryBadge.textContent = itemCategory(item);
        media.appendChild(categoryBadge);

        const info = document.createElement("div");
        info.className = "food-menu-info";

        const name = document.createElement("div");
        name.className = "food-menu-name";
        name.textContent = item.name || "Без названия";

        const footer = document.createElement("div");
        footer.className = "food-menu-card-footer";
        const price = document.createElement("span");
        price.className = "food-menu-price";
        price.textContent = money(item.retail_price);
        const addMark = document.createElement("span");
        addMark.className = "food-menu-add-mark";
        addMark.textContent = "+";
        addMark.setAttribute("aria-hidden", "true");
        footer.append(price, addMark);

        info.append(name, footer);
        button.append(media, info);

        button.addEventListener("click", () => addFoodItem(item));

        return button;
    }

    function renderFoodMenu(append = false, newItems = foodItems) {
        const grid = document.getElementById("foodMenuGrid");
        if (!grid || !foodLoaded) return;
        if (!append) grid.replaceChildren();
        if (!foodItems.length) {
            const empty = document.createElement("div");
            empty.className = "food-menu-empty";
            empty.textContent = "По этому фильтру ничего не найдено.";
            grid.appendChild(empty);
            renderFoodPagination();
            return;
        }
        // Append just the new page, without rebuilding all existing cards.
        const fragment = document.createDocumentFragment();
        newItems.forEach(item => fragment.appendChild(makeFoodCard(item)));
        grid.appendChild(fragment);
        renderFoodPagination();
    }

    function getCart() {
        try {
            return Array.isArray(cart) ? cart : [];
        } catch (error) {
            return [];
        }
    }

    function cartLineTotal(item) {
        if (typeof cartItemTotal === "function") {
            return cartItemTotal(item);
        }
        return Number(item?.price || 0) * Number(item?.qty || 0);
    }

    function cartQuantity(item) {
        if (typeof formatQuantity === "function") {
            return formatQuantity(item?.qty || 0, item?.unit || "шт");
        }
        return String(item?.qty || 0);
    }

    function renderFoodCart() {
        const root = document.getElementById("foodCart");
        const totalNode = document.getElementById("foodOrderTotal");
        const clientNode = document.getElementById("foodClientLabel");
        if (!root || !totalNode) return;

        const activeCart = getCart();
        root.innerHTML = "";

        if (!activeCart.length) {
            const empty = document.createElement("div");
            empty.className = "food-cart-empty";
            empty.textContent = "Нажмите на блюдо, чтобы добавить его в заказ";
            root.appendChild(empty);
        } else {
            activeCart.forEach((item, index) => {
                const row = document.createElement("div");
                row.className = "food-cart-row";

                const editable = item.item_type === 'dish' || !item.item_type;
                const top = document.createElement(editable ? 'button' : 'div');
                top.className = 'food-cart-row-top';
                if (editable) {
                    top.type = 'button';
                    top.classList.add('food-cart-row-editable');
                    top.title = 'Изменить добавки и состав';
                    top.setAttribute('aria-label', 'Изменить состав: ' + (item.name || 'Блюдо'));
                    top.addEventListener('click', () => { void editFoodCartItem(index); });
                }

                const name = document.createElement("div");
                name.className = "food-cart-row-name";
                name.textContent = item.name || "Позиция";
                if (editable) {
                    const hint = document.createElement("small");
                    hint.className = "food-cart-edit-hint";
                    hint.textContent = "Изменить состав";
                    name.appendChild(hint);
                }

                const price = document.createElement("div");
                price.className = "food-cart-row-price";
                price.textContent = money(cartLineTotal(item));

                top.append(name, price);
                const notes = [
                    ...(Array.isArray(item.modifiers) ? item.modifiers.map(mod => '+ ' + mod.name) : []),
                    ...(Array.isArray(item.excluded_ingredients) ? item.excluded_ingredients.map(ing => 'Без ' + ing.name) : [])
                ];
                if (notes.length) {
                    const note = document.createElement('small');
                    note.className = 'food-cart-special-instructions';
                    note.textContent = notes.join(' · ');
                    name.appendChild(note);
                }

                const bottom = document.createElement("div");
                bottom.className = "food-cart-row-bottom";

                const qty = document.createElement("div");
                qty.className = "food-qty";

                const minus = document.createElement("button");
                minus.type = "button";
                minus.textContent = "−";
                minus.addEventListener("click", () => {
                    if (typeof changeQty === "function") changeQty(index, -1);
                });

                const qtyText = document.createElement("span");
                qtyText.textContent = cartQuantity(item);

                const plus = document.createElement("button");
                plus.type = "button";
                plus.textContent = "+";
                plus.addEventListener("click", () => {
                    if (typeof changeQty === "function") changeQty(index, 1);
                });

                qty.append(minus, qtyText, plus);

                const remove = document.createElement("button");
                remove.type = "button";
                remove.className = "food-remove-btn";
                remove.textContent = "Удалить";
                remove.addEventListener("click", () => {
                    if (typeof removeItem === "function") removeItem(index);
                });

                bottom.append(qty, remove);
                row.append(top, bottom);
                root.appendChild(row);
            });
        }

        const total = activeCart.reduce((sum, item) => sum + cartLineTotal(item), 0);
        totalNode.textContent = money(total);

        if (clientNode) {
            const originalClient = document.getElementById("clientSearch");
            clientNode.textContent = originalClient?.value || "Частное лицо";
        }
    }

    function clearFoodCart() {
        try {
            resetFoodOrder();
            cart = [];
            if (typeof renderCart === "function") renderCart();
            else renderFoodCart();
        } catch (error) {
            console.error("FOOD CART CLEAR ERROR:", error);
        }
    }

    function hookSharedCartRenderer() {
        if (typeof window.renderCart === "function" && !window.renderCart.__foodHooked) {
            const originalRenderCart = window.renderCart;
            const wrapped = function(...args) {
                const result = originalRenderCart.apply(this, args);
                renderFoodCart();
                return result;
            };
            wrapped.__foodHooked = true;
            window.renderCart = wrapped;
        }

        if (typeof window.confirmClient === "function" && !window.confirmClient.__foodHooked) {
            const originalConfirmClient = window.confirmClient;
            const wrappedConfirmClient = function(...args) {
                const result = originalConfirmClient.apply(this, args);
                window.setTimeout(renderFoodCart, 0);
                return result;
            };
            wrappedConfirmClient.__foodHooked = true;
            window.confirmClient = wrappedConfirmClient;
        }
    }

    document.addEventListener('click', function(e){ if(e.target.closest('[data-food-modifier-close]')) closeFoodModifierModal(); });
    document.getElementById('foodModifierAdd')?.addEventListener('click', confirmFoodModifiers);
    document.querySelectorAll('[data-food-modifier-tab]').forEach(button => {
        button.addEventListener('click', () => setFoodModifierTab(button.dataset.foodModifierTab));
        button.addEventListener('keydown', event => {
            if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
            event.preventDefault();
            const next = button.dataset.foodModifierTab === 'add' ? 'remove' : 'add';
            setFoodModifierTab(next);
            document.getElementById(next === 'add' ? 'foodModifierAddTab' : 'foodModifierRemoveTab')?.focus();
        });
    });


    function updateFoodCheckoutControls(isFood) {
        const staged = isFood && foodCheckoutMode !== "fast";
        const external = staged && foodCheckoutMode === "external";
        document.body.classList.toggle("food-checkout-orders", staged);
        document.body.classList.toggle("food-checkout-external", external);
        document.querySelectorAll(".payment-actions > .pay-btn:not(.food-checkout-primary):not(.food-checkout-secondary)").forEach(button => {
            button.hidden = staged;
        });
        const precheck = document.getElementById("foodPrecheckCheckout");
        const pay = document.getElementById("foodCompletePayment");
        const other = document.getElementById("foodExternalPayment");
        if (precheck) precheck.hidden = !staged;
        if (pay) pay.hidden = !staged || external;
        if (other) other.hidden = !external;
        const methods = document.querySelector(".payment-methods");
        if (methods) methods.hidden = external;
    }

    let currentFoodOrderId = null;
    let currentFoodOrderSaved = false;
    let currentSavedPlannedMethod = null;
    let lastFoodPrintFingerprint = null;
    let lastFoodPrintUiSignature = null;
    let foodOrderBusy = false;
    let foodCheckoutBusy = false;
    let foodCashPrintReceived = null;
    let pendingFoodCashConfirmation = false;
    let activeFoodTicketKind = "precheck";
    let activeFoodTicketOrderId = null;
    let foodOrderPage = 1;

    function foodMessage(message) {
        const node = document.getElementById("foodOrderMessage");
        if (node) node.textContent = message || "";
    }

    function resetFoodOrder() {
        currentFoodOrderId = null;
        currentFoodOrderSaved = false;
        pendingFoodCashConfirmation = false;
        currentSavedPlannedMethod = null;
        lastFoodPrintFingerprint = null;
        lastFoodPrintUiSignature = null;
        ["foodOrderTable", "foodOrderGuest", "foodOrderNote"].forEach(id => {
            const element = document.getElementById(id);
            if (element) element.value = "";
        });
        foodMessage("");
        showFoodPrintStatus("");
    }

    function selectedFoodPaymentMethod() {
        const card = Number(String(document.getElementById("cardInput")?.value || "").replace(",", ".")) || 0;
        const kaspi = Number(String(document.getElementById("kaspiInput")?.value || "").replace(",", ".")) || 0;
        return kaspi > 0 ? "kaspi" : card > 0 ? "card" : "cash";
    }

    function applySavedFoodPaymentMethod(method, amount) {
        for (const id of ["cashInput", "cardInput", "kaspiInput"]) {
            const input = document.getElementById(id);
            if (input) input.value = "";
        }
        if (method === "card" || method === "kaspi") {
            const el = document.getElementById(method === "card" ? "cardInput" : "kaspiInput");
            if (el) el.value = String(amount || 0);
        }
    }

    async function saveFoodOrder() {
        if (foodOrderBusy) return null;
        if (!getCart().length) { foodMessage("Сначала добавьте позиции в заказ"); return null; }
        foodOrderBusy = true;
        const btn = document.getElementById("foodOrderSave");
        if (btn) btn.disabled = true;
        try {
            const response = await fetch("/api/food/orders", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({
                    id: currentFoodOrderId,
                    table_name: document.getElementById("foodOrderTable")?.value || "",
                    guest_name: document.getElementById("foodOrderGuest")?.value || "",
                    note: document.getElementById("foodOrderNote")?.value || "",
                    client_id: typeof selectedClient !== "undefined" ? selectedClient : null,
                    planned_payment_method: selectedFoodPaymentMethod(),
                    cart: getCart()
                })
            });
            const data = await response.json();
            if (!response.ok || !data.success) throw new Error(data.message || "Не удалось сохранить заказ");
            currentFoodOrderId = data.order.id;
            currentFoodOrderSaved = true;
            currentSavedPlannedMethod = data.order.planned_payment_method || "cash";
            foodMessage("Заказ №" + currentFoodOrderId + " сохранён");
            return data.order;
        } catch (error) {
            foodMessage(error.message || "Ошибка сохранения");
            return null;
        } finally {
            foodOrderBusy = false;
            if (btn) btn.disabled = false;
        }
    }


    function showFoodPrintStatus(text, hasError = false) {
        const status = document.getElementById("foodPrintStatus");
        if (!status) return;
        status.hidden = !text;
        status.textContent = text || "";
        status.classList.toggle("is-error", hasError);
    }

    function getFoodDesktopBridge() {
        try { return window.nikaDesktop || window.parent?.nikaDesktop || null; }
        catch (_) { return window.nikaDesktop || null; }
    }

    function isElectronFoodCheckout() {
        // Runtime, not a company setting or user agent. The preload sets this
        // only inside Nika Electron, including its embedded sales iframe.
        return getFoodDesktopBridge()?.isElectron === true;
    }

    function getFoodPrinterBridge() {
        return isElectronFoodCheckout() ? (getFoodDesktopBridge()?.printers || null) : null;
    }

    async function getSavedFoodTicketHtml(orderId, kind) {
        const cashReceived = kind === "precheck" ? Number(foodCashPrintReceived || 0) : 0;
        const suffix = cashReceived > 0 ? "&cash_received=" + encodeURIComponent(cashReceived) : "";
        const response = await fetch("/food/orders/" + encodeURIComponent(orderId) +
            "/ticket/" + kind + "?embed=1" + suffix, {credentials:"same-origin", cache:"no-store"});
        if (!response.ok) throw new Error("Не удалось загрузить " +
            (kind === "kitchen" ? "заказ на кухню" : "пречек гостю"));
        const html = await response.text();
        const doc = new DOMParser().parseFromString(html, "text/html");
        if (!doc.body || !doc.querySelector(".item")) {
            throw new Error("Пустой документ " + kind + ": печать не запущена");
        }
        const page = doc.body.cloneNode(true);
        page.querySelectorAll(".actions,script").forEach(node => node.remove());
        const styles = Array.from(doc.querySelectorAll("style"))
            .map(node => node.textContent || "").join("\n")
            .replace(/@page\s*\{[^}]*\}/gi, "");
        // Electron's receiptPage selects the paper width from the appropriate
        // printer setting (guest or kitchen); never force a 76mm-width ticket.
        return '<style>' + styles +
            '.receipt.food-ticket-paper{width:100%;max-width:100%;padding:2mm 0;margin:0;}' +
            '.receipt.food-ticket-paper .item{min-width:0;}' +
            '</style><main class="receipt food-ticket-paper">' + page.innerHTML + '</main>';
    }

    function savedFoodTicketFingerprint(order) {
        return JSON.stringify({
            cart: order.cart, table: order.table_name, guest: order.guest_name,
            note: order.note, client: order.client_id,
            payment: order.planned_payment_method || "cash"
        });
    }

    function currentFoodUiSignature() {
        // The browser cart differs from the server-normalized cart: compare
        // snapshots taken in the same representation, not raw/server JSON.
        return JSON.stringify({
            // Only stable checkout data belongs to the print gate. Customer
            // fields and server-normalized metadata may change during render.
            cart: getCart().map(item => ({
                id: Number(item.id), qty: Number(item.qty), price: Number(item.price),
                modifiers: item.modifiers || [],
                excluded_ingredients: item.excluded_ingredients || []
            })),
            payment: selectedFoodPaymentMethod()
        });
    }

    function isFoodTicketCurrent() {
        return Boolean(currentFoodOrderId && currentFoodOrderSaved &&
            lastFoodPrintFingerprint && lastFoodPrintUiSignature &&
            currentSavedPlannedMethod === selectedFoodPaymentMethod() &&
            lastFoodPrintUiSignature === currentFoodUiSignature());
    }

    async function printBothFoodTickets(order, {manualAllowed = false} = {}) {
        const printers = getFoodPrinterBridge();
        const fingerprint = savedFoodTicketFingerprint(order);
        const uiSnapshotBeforePrint = currentFoodUiSignature();
        if (!isElectronFoodCheckout()) {
            // In the website, both documents are preview-only. No local printer
            // probing and no mandatory printing before a valid payment.
            openFoodTicketPair(order.id);
            const msg = "Заказ №" + order.id + " сохранён. Чек гостю и заказ на кухню открыты для просмотра, сохранения и отправки.";
            foodMessage(msg);
            showFoodPrintStatus(msg);
            lastFoodPrintFingerprint = fingerprint;
            lastFoodPrintUiSignature = uiSnapshotBeforePrint;
            return true;
        }
        if (!printers?.printFoodOrder) {
            const msg = "В Electron недоступен сервис печати двух чеков. Проверьте подключение принтеров.";
            foodMessage(msg);
            showFoodPrintStatus(msg, true);
            return false;
        }

        // Same order and payment => no duplicated ticket jobs.
        const [guestTicket, kitchenTicket] = await Promise.allSettled([
            getSavedFoodTicketHtml(order.id, "precheck"),
            getSavedFoodTicketHtml(order.id, "kitchen")
        ]);
        // If either template could not be built, do not spool a misleading
        // partial order, especially when the same device prints both receipts.
        if (guestTicket.status !== "fulfilled" || kitchenTicket.status !== "fulfilled") {
            const cause = guestTicket.status === "rejected"
                ? guestTicket.reason : kitchenTicket.reason;
            throw new Error(cause?.message || "Не удалось подготовить оба чека");
        }
        const results = await printers.printFoodOrder({
            orderId: order.id,
            fingerprint,
            guestHtml: guestTicket.value,
            kitchenHtml: kitchenTicket.value
        });

        const guest = results?.guest;
        const kitchen = results?.kitchen;
        const guestStatus = guest?.success
            ? (guest.alreadySent ? "гостевой чек уже отправлен" : "гостевой чек отправлен")
            : "ГОСТЬ: " + (guest?.error || guestTicket.reason?.message || "ошибка печати");
        const kitchenStatus = kitchen?.skipped ? "кухня не настроена"
            : kitchen?.success
                ? (kitchen.alreadySent ? "кухонный чек уже отправлен" : "кухонный чек отправлен")
                : "КУХНЯ: " + (kitchen?.error || kitchenTicket.reason?.message || "ошибка печати");
        const message = "Заказ №" + order.id + " сохранён · " + guestStatus + " · " + kitchenStatus;
        foodMessage(message);
        showFoodPrintStatus(message, guest?.success === false || kitchen?.success === false);
        if (!results?.success || !guest?.success || !kitchen?.success) {
            // A second click retries only the failed spool job.
            console.warn("FOOD PRINT PARTIAL FAILURE:", results);
            return false;
        }
        lastFoodPrintFingerprint = fingerprint;
        lastFoodPrintUiSignature = uiSnapshotBeforePrint;
        return true;
    }

    async function createFoodPrecheck() {
        if (foodCheckoutBusy) return;
        showFoodPrintStatus("");
        if (!getCart().length) { foodMessage("Добавьте блюдо в заказ"); return; }
        foodCheckoutBusy = true;
        const button = document.getElementById("foodPrecheckCheckout");
        if (button) button.disabled = true;
        try {
            // Always save the freshest cart before opening the precheck.
            const saved = await saveFoodOrder();
            if (saved) {
                foodMessage("Заказ №" + saved.id + " оформлен");
                try {
                    const completed = await printBothFoodTickets(saved, {manualAllowed: true});
                    if (!completed) {
                        foodMessage("Заказ №" + saved.id + " сохранён, но печать не завершена. Проверьте настройки принтеров.");
                    }
                } catch (error) {
                    console.error("DUAL FOOD PRINT ERROR:", error);
                    const message = "Заказ №" + saved.id + " сохранён, но печать не удалась: " + (error.message || error);
                    foodMessage(message);
                    showFoodPrintStatus(message, true);
                }
            }
        } finally {
            foodCheckoutBusy = false;
            if (button) button.disabled = false;
        }
    }

    async function finalizeFoodPaymentAfterChecks(method, received = 0) {
        const websiteMode = !isElectronFoodCheckout();
        const needsFreshTickets = !isFoodTicketCurrent();
        if (needsFreshTickets) {
            const saved = await saveFoodOrder();
            if (!saved) return false;
            if (!websiteMode) {
                // Electron still requires successful spooling of BOTH tickets
                // before the sale. Its printer config and retry gate stay intact.
                foodCashPrintReceived = method === "cash" ? received : null;
                try {
                    if (!await printBothFoodTickets(saved)) {
                        foodMessage("Заказ сохранён, но оба чека не распечатаны. Оплата не проведена.");
                        return false;
                    }
                } catch (error) {
                    foodMessage("Заказ сохранён, ошибка печати: " + (error.message || error));
                    showFoodPrintStatus("Оплата не проведена: проверьте принтеры.", true);
                    return false;
                } finally {
                    foodCashPrintReceived = null;
                }
            }
            // Website: do NOT check local printers or block payment.
        }
        const browserOrderId = websiteMode && needsFreshTickets ? currentFoodOrderId : null;

        const total = getCart().reduce((sum, item) =>
            sum + Number(item.price || 0) * Number(item.qty || 0), 0);
        if (method === "cash") {
            if (received + 0.009 < total) {
                foodMessage("Полученная сумма меньше суммы заказа");
                return false;
            }
            const paid = await submitSalePayment({
                paymentMethod:"cash", cash:received, card:0, kaspi:0,
                cashChange:Math.max(0, received-total)
            });
            if (paid && browserOrderId) openFoodTicketPair(browserOrderId);
            return paid;
        }
        const card = Number(String(document.getElementById("cardInput")?.value || "").replace(",", ".")) || 0;
        const kaspi = Number(String(document.getElementById("kaspiInput")?.value || "").replace(",", ".")) || 0;
        const paid = await submitSalePayment({
            paymentMethod:method, cash:0,
            card:method === "card" ? card : 0,
            kaspi:method === "kaspi" ? kaspi : 0, cashChange:0
        });
        if (paid && browserOrderId) openFoodTicketPair(browserOrderId);
        return paid;
    }

    async function payExistingFoodOrder() {
        if (foodCheckoutBusy) return;
        showFoodPrintStatus("");
        if (!getCart().length) { foodMessage("Сначала добавьте блюда в корзину"); return; }
        if (window.nikaKaspiPosActive) {
            foodMessage("Дождитесь завершения оплаты на Kaspi POS");
            return;
        }
        foodCheckoutBusy = true;
        const button = document.getElementById("foodCompletePayment");
        if (button) button.disabled = true;
        try {
            // Stock warning precedes any new print job for ALL tenders.
            if (typeof window.nikaConfirmNegativeStockSale === "function" &&
                !(await window.nikaConfirmNegativeStockSale())) return;
            const method = selectedFoodPaymentMethod();
            if (method === "cash") {
                // Cash amount must be known before rendering the guest precheck.
                // The modal's confirm handler continues through the same checkout.
                pendingFoodCashConfirmation = true;
                openCashChangeModal();
                return;
            }
            await finalizeFoodPaymentAfterChecks(method);
        } finally {
            foodCheckoutBusy = false;
            if (button) button.disabled = false;
        }
    }

    async function confirmFoodCashPayment(event) {
        if (!pendingFoodCashConfirmation || currentMode() !== "food") return;
        event.preventDefault();
        event.stopImmediatePropagation();
        if (foodCheckoutBusy) return;
        const received = Number(String(document.getElementById("cashReceivedInput")?.value || "").replace(",", ".")) || 0;
        const total = getCart().reduce((sum, item) =>
            sum + Number(item.price || 0) * Number(item.qty || 0), 0);
        if (received + 0.009 < total) {
            renderCashChange();
            return;
        }
        foodCheckoutBusy = true;
        const button = document.getElementById("cashChangeConfirm");
        if (button) button.disabled = true;
        try {
            document.getElementById("cashInput").value = String(received);
            const successful = await finalizeFoodPaymentAfterChecks("cash", received);
            if (successful) {
                pendingFoodCashConfirmation = false;
                closeCashChangeModal(true);
            }
        } finally {
            foodCheckoutBusy = false;
            if (button) button.disabled = false;
        }
    }

    function newFoodOrder() {
        if (getCart().length && !window.confirm(currentFoodOrderSaved
            ? "Начать новый заказ? Сохранённый останется в истории."
            : "Текущий заказ не сохранён. Очистить корзину?")) return;
        clearFoodCart();
        applySavedFoodPaymentMethod("cash", 0);
        foodMessage("Новый заказ");
        showFoodPrintStatus("");
    }

    function setExternalModal(open) {
        const modal = document.getElementById("foodExternalModal");
        if (modal) modal.hidden = !open;
        if (open) {
            const input = document.getElementById("foodExternalReceiptNumber");
            if (input) { input.value = ""; input.focus(); }
            const error = document.getElementById("foodExternalError");
            if (error) error.textContent = "";
        }
    }

    async function openExternalPayment() {
        if (foodCheckoutBusy || foodCheckoutMode !== "external") return;
        foodCheckoutBusy = true;
        try {
            const saved = await saveFoodOrder();
            if (saved) setExternalModal(true);
        } finally { foodCheckoutBusy = false; }
    }

    async function confirmExternalPayment() {
        const receipt = document.getElementById("foodExternalReceiptNumber")?.value?.trim() || "";
        const errorNode = document.getElementById("foodExternalError");
        if (!receipt) { if (errorNode) errorNode.textContent = "Укажите номер внешнего фискального чека"; return; }
        if (foodCheckoutBusy || !currentFoodOrderSaved || !currentFoodOrderId) return;
        foodCheckoutBusy = true;
        const button = document.getElementById("foodExternalConfirm");
        if (button) button.disabled = true;
        try {
            const response = await fetch("/api/food/orders/" + currentFoodOrderId + "/external-payment", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({receipt_number: receipt})
            });
            const data = await response.json();
            if (!response.ok || !data.success) throw new Error(data.message || "Не удалось подтвердить чек");
            setExternalModal(false);
            clearFoodCart();
            foodMessage("Чек №" + receipt + " отмечен · учёт продаж и склада Nika не изменён");
        } catch (error) {
            if (errorNode) errorNode.textContent = error.message || "Ошибка внешней оплаты";
        } finally {
            foodCheckoutBusy = false;
            if (button) button.disabled = false;
        }
    }

    function setFoodDetails(open) {
        const modal = document.getElementById("foodOrderDetailsModal");
        if (modal) modal.hidden = !open;
    }
    function foodTicketUrl(orderId, kind, pdf = false) {
        const path = pdf ? "ticket-pdf/" : "ticket/";
        return "/food/orders/" + encodeURIComponent(orderId) + "/" + path + kind;
    }

    function openFoodTicketPair(orderId) {
        if (!orderId) return;
        const modal = document.getElementById("foodTicketModal");
        const single = document.getElementById("foodTicketSingle");
        const pair = document.getElementById("foodTicketPair");
        if (!modal || !single || !pair) return;
        if (modal.parentElement !== document.body) document.body.appendChild(modal);
        activeFoodTicketOrderId = orderId;
        document.getElementById("foodTicketHeading").textContent = "Заказ №" + orderId + " · два чека";
        modal.querySelector(".food-ticket-dialog")?.classList.add("is-dual");
        single.hidden = true;
        pair.hidden = false;
        document.getElementById("foodGuestTicketFrame").src = foodTicketUrl(orderId, "precheck") + "?embed=1";
        document.getElementById("foodKitchenTicketFrame").src = foodTicketUrl(orderId, "kitchen") + "?embed=1";
        modal.hidden = false;
    }

    function openFoodTicket(orderId, kind, autoPrint = false) {
        if (!orderId) { foodMessage("Сначала сохраните заказ"); return; }
        const modal = document.getElementById("foodTicketModal");
        const frame = document.getElementById("foodTicketFrame");
        if (!modal || !frame) return;
        if (modal.parentElement !== document.body) document.body.appendChild(modal);
        activeFoodTicketOrderId = orderId;
        activeFoodTicketKind = kind;
        document.getElementById("foodTicketHeading").textContent = kind === "kitchen" ? "Заказ на кухню" : "Чек гостю";
        modal.querySelector(".food-ticket-dialog")?.classList.remove("is-dual");
        document.getElementById("foodTicketPair").hidden = true;
        document.getElementById("foodTicketSingle").hidden = false;
        const printButton = document.getElementById("foodTicketPrint");
        if (printButton) printButton.disabled = true;
        frame.onload = () => {
            if (printButton) printButton.disabled = false;
            if (autoPrint && kind === "precheck" && isElectronFoodCheckout()) {
                // Never auto-print a browser preview. Electron's combined
                // printFoodOrder is the normal two-printer checkout path.
                void printFoodTicketFromModal();
            }
        };
        frame.src = foodTicketUrl(orderId, kind) + "?embed=1";
        modal.hidden = false;
    }

    function closeFoodTicket() {
        const modal = document.getElementById("foodTicketModal");
        if (modal) modal.hidden = true;
        for (const id of ["foodTicketFrame", "foodGuestTicketFrame", "foodKitchenTicketFrame"]) {
            const frame = document.getElementById(id);
            if (frame) { frame.onload = null; frame.src = "about:blank"; }
        }
        activeFoodTicketOrderId = null;
    }

    async function foodTicketFile(orderId, kind) {
        const result = await fetch(foodTicketUrl(orderId, kind, true), {
            credentials: "same-origin", headers: {Accept:"application/pdf"}
        });
        if (result.ok && (result.headers.get("content-type") || "").includes("application/pdf")) {
            return {
                blob: await result.blob(),
                filename: "nika-order-" + orderId + "-" + (kind === "kitchen" ? "kitchen" : "guest") + ".pdf",
                mime: "application/pdf"
            };
        }
        if (result.status === 403 || result.status === 404) throw new Error("Чек недоступен");
        // WeasyPrint is optional on older VPSs. Saving/sharing an HTML copy
        // must still work even if server-side PDF generation is unavailable.
        const html = await fetch(foodTicketUrl(orderId, kind) + "?embed=1", {
            credentials: "same-origin"
        });
        if (!html.ok) throw new Error("Не удалось получить чек");
        return {
            blob: new Blob([await html.text()], {type:"text/html;charset=utf-8"}),
            filename: "nika-order-" + orderId + "-" + (kind === "kitchen" ? "kitchen" : "guest") + ".html",
            mime: "text/html"
        };
    }

    function downloadFoodTicketFile({blob, filename}) {
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.setTimeout(() => URL.revokeObjectURL(url), 30000);
    }

    async function exportFoodTicket(kind, action, button) {
        if (!activeFoodTicketOrderId || button?.disabled) return;
        if (button) button.disabled = true;
        try {
            const fileData = await foodTicketFile(activeFoodTicketOrderId, kind);
            if (action === "share" && navigator.share && typeof File !== "undefined") {
                const file = new File([fileData.blob], fileData.filename, {type:fileData.mime});
                if (!navigator.canShare || navigator.canShare({files:[file]})) {
                    await navigator.share({
                        title: kind === "kitchen" ? "Заказ на кухню" : "Чек гостю",
                        files: [file]
                    });
                    return;
                }
            }
            downloadFoodTicketFile(fileData);
            if (action === "share") {
                foodMessage("На этом устройстве отправка файлов недоступна. Чек сохранён для отправки.");
            }
        } catch (error) {
            if (error?.name !== "AbortError") {
                console.error("FOOD TICKET EXPORT:", error);
                foodMessage(error?.message || "Не удалось сохранить чек");
            }
        } finally {
            if (button) button.disabled = false;
        }
    }

    async function printFoodTicketFromModal(kind = activeFoodTicketKind, frameOverride = null, buttonOverride = null) {
        const frame = frameOverride || document.getElementById("foodTicketFrame");
        const button = buttonOverride || document.getElementById("foodTicketPrint");
        if (!frame || !frame.contentDocument?.body || button?.disabled) return;
        const doc = frame.contentDocument;
        if (!doc.querySelector(".item")) {
            foodMessage("Чек ещё загружается, повторите печать");
            return;
        }
        const title = kind === "kitchen" ? "Заказ на кухню" : "Чек гостю";
        const printers = getFoodPrinterBridge();
        const printMethod = kind === "kitchen"
            ? printers?.printKitchen : printers?.printReceipt;
        if (!printMethod) {
            frame.contentWindow?.print();
            return;
        }
        if (button) button.disabled = true;
        try {
            const page = doc.body.cloneNode(true);
            page.querySelectorAll(".actions,script").forEach(node => node.remove());
            const styles = Array.from(doc.querySelectorAll("style"))
                .map(node => node.textContent || "").join("\n")
                .replace(/@page\s*\{[^}]*\}/gi, "");
            const html = '<style>' + styles +
                '.receipt.food-ticket-paper{width:100%;max-width:100%;padding:2mm 0;margin:0;}' +
                '.receipt.food-ticket-paper .item{min-width:0;}' +
                '</style><main class="receipt food-ticket-paper">' + page.innerHTML + '</main>';
            const result = await printMethod({html, title});
            if (result?.success === false) throw new Error(result.error || "Принтер отклонил чек");
            foodMessage("Документ отправлен на чековый принтер");
        } catch (error) {
            console.error("FOOD RECEIPT PRINTER:", error);
            foodMessage(error.message || "Ошибка печати через Electron");
        } finally {
            if (button) button.disabled = false;
        }
    }

    function printFoodTicket(kind) {
        if (!currentFoodOrderId || !currentFoodOrderSaved) {
            foodMessage("Сначала сохраните заказ");
            return;
        }
        openFoodTicket(currentFoodOrderId, kind);
    }

    async function openFoodOrder(id) {
        try {
            const response = await fetch("/api/food/orders/" + id);
            const data = await response.json();
            if (!response.ok || !data.success) throw new Error(data.message || "Заказ не найден");
            if (data.order.status !== "open") {
                foodMessage("Закрытый заказ доступен только для просмотра документов");
                return;
            }
            cart = data.order.cart.map(item => ({...item}));
            if (typeof renderCart === "function") renderCart();
            currentFoodOrderId = data.order.id;
            currentFoodOrderSaved = true;
            currentSavedPlannedMethod = data.order.planned_payment_method || "cash";
            lastFoodPrintFingerprint = null; // Reopened order: never assume the printer ran.
            lastFoodPrintUiSignature = null;
            applySavedFoodPaymentMethod(currentSavedPlannedMethod, data.order.total_amount);
            document.getElementById("foodOrderTable").value = data.order.table_name || "";
            document.getElementById("foodOrderGuest").value = data.order.guest_name || "";
            document.getElementById("foodOrderNote").value = data.order.note || "";
            if (typeof switchSalesTab === "function") switchSalesTab("cart");
            foodMessage("Открыт заказ №" + currentFoodOrderId);
        } catch (error) {
            foodMessage(error.message || "Не удалось открыть заказ");
        }
    }

    // The receipt is already paid: reuse Nika's audited sale refund flow.
    // Never mutate a paid food_order directly or pretend that Kaspi/reKassa
    // returned funds without invoking the corresponding payment pipeline.
    async function refundPaidFoodOrder(order, button) {
        if (button?.disabled || foodOrderBusy || foodCheckoutBusy) return;
        if (order.status !== "paid" || !Number.isSafeInteger(Number(order.sale_id)) ||
            Number(order.sale_id) <= 0) return;
        if (typeof refundSale !== "function") {
            const notice = document.getElementById("foodOrderHistoryNotice");
            if (notice) {
                notice.textContent = "Модуль возвратов недоступен. Обновите страницу.";
                notice.classList.add("is-error");
                notice.hidden = false;
            }
            return;
        }
        // refundSale confirms the financial/fiscal transaction itself.
        // After a successful refund it broadcasts nika:sale-refunded and
        // the history switches from "Оплачен" to "Возврат".
        await refundSale(Number(order.sale_id), button);
    }

    async function cancelFoodOrder(orderId, button) {
        if (button?.disabled || foodOrderBusy || foodCheckoutBusy) return;
        const message = "Отменить заказ №" + orderId + "?\n\n" +
            "Отмена доступна только до оплаты. Заказ останется в истории со статусом «Отменён».\n" +
            "Продажи, возврата денег и движения склада не будет.\n\n" +
            "Если пречек или заказ на кухню уже напечатан, предупредите сотрудников: бумажные чеки не аннулируются.";
        if (!window.confirm(message)) return;

        const notice = document.getElementById("foodOrderHistoryNotice");
        if (notice) notice.hidden = true;
        if (button) {
            button.disabled = true;
            button.textContent = "Отменяем…";
        }
        try {
            const response = await fetch("/api/food/orders/" + encodeURIComponent(orderId), {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({action: "cancel"})
            });
            const data = await response.json();
            if (!response.ok || !data.success) {
                throw new Error(data.message || "Не удалось отменить заказ");
            }
            // Do not allow a cancelled saved order to remain ready for checkout.
            if (Number(currentFoodOrderId) === Number(orderId)) {
                clearFoodCart();
                applySavedFoodPaymentMethod("cash", 0);
            }
            if (notice) {
                notice.textContent = "Заказ №" + orderId + " отменён. Оплата и склад не затронуты.";
                notice.classList.remove("is-error");
                notice.hidden = false;
            }
            try {
                await loadFoodOrderHistory();
            } catch (refreshError) {
                console.warn("Не удалось обновить историю после отмены:", refreshError);
            }
        } catch (error) {
            if (notice) {
                notice.textContent = error.message || "Не удалось отменить заказ";
                notice.classList.add("is-error");
                notice.hidden = false;
            }
        } finally {
            if (button?.isConnected) {
                button.disabled = false;
                button.textContent = "Отменить заказ";
            }
        }
    }

    async function loadFoodOrderHistory(append = false) {
        if (!append) foodOrderPage = 1;
        const filter = document.getElementById("foodOrderStatusFilter")?.value || "all";
        const response = await fetch("/api/food/orders?status=" + encodeURIComponent(filter) +
                                     "&page=" + foodOrderPage);
        const data = await response.json();
        if (!response.ok || !data.success) { foodMessage(data.message || "Ошибка истории"); return; }
        const list = document.getElementById("foodOrderHistoryList");
        if (!append) list.replaceChildren();
        if (!append && !(data.orders || []).length) {
            const empty = document.createElement("div");
            empty.className = "food-history-empty";
            empty.textContent = "Заказов с выбранным статусом пока нет";
            list.appendChild(empty);
        }
        for (const order of data.orders || []) {
            const row = document.createElement("div");
            row.className = "food-history-row";
            const label = document.createElement("div");
            label.className = "food-history-info";
            const title = document.createElement("strong");
            title.textContent = "Заказ №" + order.id + " · " + (order.table_name || "Без стола");
            const details = document.createElement("div");
            details.className = "food-history-details";
            const badge = document.createElement("span");
            badge.className = "food-history-badge food-history-badge-" +
                (["paid", "open", "external_paid", "cancelled"].includes(order.status) ? order.status : "open");
            badge.textContent = order.status === "paid" ? "Оплачен"
                : order.status === "refunded" ? "Возврат"
                : order.status === "external_paid" ? "Внешняя ККМ"
                : order.status === "cancelled" ? "Отменён" : "Ожидает оплаты";
            const total = document.createElement("span");
            total.className = "food-history-amount";
            total.textContent = money(order.total_amount);
            const time = document.createElement("span");
            time.className = "food-history-time";
            time.textContent = order.created_at_display || String(order.created_at || "").slice(0, 16).replace("T", " ");
            details.append(badge, total, time);
            label.append(title, details);

            const buttons = document.createElement("div");
            buttons.className = "food-history-actions";
            if (order.status === "open") {
                const open = document.createElement("button");
                open.type = "button";
                open.textContent = "Открыть заказ";
                open.addEventListener("click", () => openFoodOrder(order.id));
                buttons.appendChild(open);
                const cancel = document.createElement("button");
                cancel.type = "button";
                cancel.className = "food-history-cancel";
                cancel.textContent = "Отменить заказ";
                cancel.addEventListener("click", () => cancelFoodOrder(order.id, cancel));
                buttons.appendChild(cancel);
            } else if (order.status === "paid" && Number(order.sale_id) > 0) {
                const refund = document.createElement("button");
                refund.type = "button";
                refund.className = "food-history-refund";
                refund.textContent = "Оформить возврат";
                refund.title = "Возврат оплаты и фискального чека через механизм Nika Business";
                refund.addEventListener("click", () => refundPaidFoodOrder(order, refund));
                buttons.appendChild(refund);
            }
            for (const [kind, caption] of [["kitchen","Кухня"],["precheck","Пречек"]]) {
                const print = document.createElement("button");
                print.type = "button";
                print.textContent = caption;
                print.addEventListener("click", () => openFoodTicket(order.id, kind));
                buttons.appendChild(print);
            }
            row.append(label, buttons);
            list.appendChild(row);
        }
        foodOrderPage += 1;
        const more = document.getElementById("foodOrderHistoryMore");
        if (more) more.hidden = !data.has_more;
    }

    function initFoodOrderControls() {
        if (!["foodservice", "universal"].includes(window.NIKA_BUSINESS_MODE)) return;
        document.getElementById("foodOrderSave")?.addEventListener("click", saveFoodOrder);
        for (const id of ["cashInput", "cardInput", "kaspiInput"]) {
            document.getElementById(id)?.addEventListener("click", () => {
                if (!getCart().length) showFoodPrintStatus("");
            });
        }
        document.getElementById("foodOrderNew")?.addEventListener("click", newFoodOrder);
        document.getElementById("foodPrecheckCheckout")?.addEventListener("click", createFoodPrecheck);
        document.getElementById("foodCompletePayment")?.addEventListener("click", payExistingFoodOrder);
        document.getElementById("cashChangeConfirm")?.addEventListener("click", confirmFoodCashPayment, true);
        document.getElementById("foodExternalPayment")?.addEventListener("click", openExternalPayment);
        document.getElementById("foodExternalConfirm")?.addEventListener("click", confirmExternalPayment);
        document.querySelectorAll("[data-food-external-close]").forEach(el => el.addEventListener("click", () => setExternalModal(false)));
        document.getElementById("foodOrderKitchen")?.addEventListener("click", () => printFoodTicket("kitchen"));
        document.getElementById("foodOrderPrecheck")?.addEventListener("click", () => printFoodTicket("precheck"));
        document.getElementById("foodOrderDetails")?.addEventListener("click", () => setFoodDetails(true));
        document.querySelectorAll("[data-food-details-close]").forEach(el => el.addEventListener("click", () => setFoodDetails(false)));
        document.querySelectorAll("[data-food-ticket-close]").forEach(el => el.addEventListener("click", closeFoodTicket));
        document.getElementById("foodTicketModal")?.addEventListener("click", event => {
            const button = event.target.closest("[data-food-ticket-action]");
            if (!button) return;
            const kind = button.dataset.foodTicketKind || activeFoodTicketKind;
            const action = button.dataset.foodTicketAction;
            if (action === "print") {
                const frame = button.dataset.foodTicketKind
                    ? document.getElementById(kind === "kitchen" ? "foodKitchenTicketFrame" : "foodGuestTicketFrame")
                    : document.getElementById("foodTicketFrame");
                void printFoodTicketFromModal(kind, frame, button);
            } else if (action === "save" || action === "share") {
                void exportFoodTicket(kind, action, button);
            }
        });
        document.addEventListener("keydown", event => {
            if (event.key === "Escape") { setFoodDetails(false); closeFoodTicket(); setExternalModal(false); }
        });
        document.getElementById("foodOrderStatusFilter")?.addEventListener("change", () => loadFoodOrderHistory());
        document.getElementById("foodOrderHistoryMore")?.addEventListener("click", () => loadFoodOrderHistory(true));
        for (const id of ["foodOrderTable", "foodOrderGuest", "foodOrderNote"]) {
            document.getElementById(id)?.addEventListener("input", () => { currentFoodOrderSaved = false; });
        }
        window.addEventListener("nika:sale-completed", resetFoodOrder);
        window.addEventListener("nika:sale-refunded", () => {
            const history = document.getElementById("foodOrdersWorkspace");
            if (history && !history.hidden) {
                void loadFoodOrderHistory();
            }
        });
    }

    function initFoodSalesMode() {
        document.getElementById("salesModeRetail")?.addEventListener("click", () => setMode("retail"));
        document.getElementById("salesModeFood")?.addEventListener("click", () => setMode("food"));
        document.getElementById("foodSearch")?.addEventListener("input", () => {
            clearTimeout(foodSearchTimer);
            foodSearchTimer = setTimeout(refreshFoodMenu, 280);
        });
        document.getElementById("foodMenuLoadMore")?.addEventListener("click", fetchFoodPage);
        document.querySelectorAll("[data-food-section]").forEach(button =>
            button.addEventListener("click", () => selectFoodSection(button.dataset.foodSection)));
        updateFoodQuickFilters();
        document.getElementById("foodCategoryToggle")?.addEventListener("click", () => {
            const popover = document.getElementById("foodCategoryPopover");
            if (popover) setFoodCategoryPopover(popover.hidden);
        });
        document.getElementById("foodCategorySearch")?.addEventListener("input", filterFoodCategories);
        document.addEventListener("click", event => {
            const chooser = document.getElementById("foodCategoryChooser");
            if (chooser && !chooser.contains(event.target)) setFoodCategoryPopover(false);
        });
        document.addEventListener("keydown", event => {
            if (event.key === "Escape" && !document.getElementById("foodCategoryPopover")?.hidden) {
                setFoodCategoryPopover(false);
                document.getElementById("foodCategoryToggle")?.focus();
            }
        });
        document.getElementById("foodClearCart")?.addEventListener("click", clearFoodCart);
        document.getElementById("foodClientButton")?.addEventListener("click", () => {
            if (typeof openClientSheet === "function") openClientSheet();
        });

        hookSharedCartRenderer();
        initFoodOrderControls();
        setMode(currentMode());
        renderFoodCart();

        window.addEventListener("nika:sale-completed", renderFoodCart);
    }

    window.NikaFoodSales = {
        setMode,
        reloadMenu: () => {
            return loadFoodMenu(true);
        },
        renderCart: renderFoodCart,
        loadHistory: () => loadFoodOrderHistory(),
        isFoodMode: () => currentMode() === "food",
        getSavedOrderId: () => currentFoodOrderSaved ? currentFoodOrderId : null,
        clearOrder: resetFoodOrder,
        paymentNotice: (message) => {
            // Do not leave a permanent green "already paid" badge on the next
            // empty/new order. Printed receipts remain accessible in history.
            showFoodPrintStatus("");
            foodMessage(message);
            window.setTimeout(() => {
                const node = document.getElementById("foodOrderMessage");
                if (node && node.textContent === message) node.textContent = "";
            }, 5500);
        }
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initFoodSalesMode, { once: true });
    } else {
        initFoodSalesMode();
    }
})();