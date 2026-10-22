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
            if (grid) grid.scrollTop = 0;
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
            foodItems.push(...(data.items || []));
            foodPage++;
            foodHasMore = Boolean(data.has_more);
            foodLoaded = true;
            renderFoodMenu();
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

    function openFoodModifierModal(item, groups, ingredients) {
        pendingModifierItem = item;
        pendingModifierGroups = groups;
        pendingRecipeIngredients = ingredients;
        const modal = document.getElementById('foodModifierModal');
        const root = document.getElementById('foodModifierGroups');
        document.getElementById('foodModifierTitle').textContent = item.name || 'Блюдо';
        root.innerHTML = '';
        if (ingredients.length) {
            const section = document.createElement('section');
            section.className = 'food-modifier-group food-exclusions-group';
            const heading = document.createElement('div');
            heading.className = 'food-modifier-group-title';
            heading.innerHTML = '<strong>Убрать из состава</strong><small>Без доплаты, цена не меняется</small>';
            section.appendChild(heading);
            ingredients.forEach(ingredient => {
                const label = document.createElement('label');
                label.className = 'food-modifier-option food-exclusion-option';
                const input = document.createElement('input');
                input.type = 'checkbox';
                input.dataset.excludedIngredientId = String(ingredient.item_id);
                const name = document.createElement('span');
                name.textContent = 'Без ' + (ingredient.name || 'ингредиента');
                label.append(input, name);
                section.appendChild(label);
            });
            root.appendChild(section);
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
            root.appendChild(section);
        });
        modal.hidden = false;
        renderFoodModifierTotal();
    }
    function escapeFood(v){const d=document.createElement('div');d.textContent=String(v||'');return d.innerHTML;}
    function selectedFoodModifiers(){const selected=[];document.querySelectorAll('#foodModifierGroups input:checked').forEach(input=>{const g=pendingModifierGroups.find(x=>String(x.id)===String(input.dataset.groupId));const o=g?.options?.find(x=>String(x.id)===String(input.value));if(o)selected.push(o)});return selected}
    function renderFoodModifierTotal(){const extra=selectedFoodModifiers().reduce((s,o)=>s+Number(o.price_delta||0),0);const total=Number(pendingModifierItem?.retail_price||0)+extra;const n=document.getElementById('foodModifierTotal');if(n)n.textContent=money(total)}
    function closeFoodModifierModal(){const m=document.getElementById('foodModifierModal');if(m)m.hidden=true;pendingModifierItem=null;pendingModifierGroups=[];pendingRecipeIngredients=[]}
    function confirmFoodModifiers(){
        if(!pendingModifierItem)return;
        for(const group of pendingModifierGroups){const count=document.querySelectorAll('#foodModifierGroups input[data-group-id="'+group.id+'"]:checked').length;if(count<Number(group.min_select||0)){alert('Выберите: '+group.name);return}}
        const mods=selectedFoodModifiers(); const price=Number(pendingModifierItem.retail_price||0)+mods.reduce((s,o)=>s+Number(o.price_delta||0),0);
        const excludedIngredients = Array.from(document.querySelectorAll('#foodModifierGroups input[data-excluded-ingredient-id]:checked')).map(input => {
            const ingredient = pendingRecipeIngredients.find(row => String(row.item_id) === input.dataset.excludedIngredientId);
            return {id:Number(ingredient.item_id),name:ingredient.name};
        });
        cart.push({id:Number(pendingModifierItem.id),name:pendingModifierItem.name||'Блюдо',price:price,qty:1,gtin:pendingModifierItem.gtin||'',ntin:pendingModifierItem.ntin||'',unit:pendingModifierItem.unit||'шт',item_type:'dish',modifiers:mods.map(o=>({id:o.id,name:o.name,price_delta:Number(o.price_delta||0)})),excluded_ingredients:excludedIngredients});
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
            img.src = item.image;
            img.alt = "";
            img.loading = "lazy";
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

    function renderFoodMenu() {
        const grid = document.getElementById("foodMenuGrid");
        if (!grid || !foodLoaded) return;
        grid.innerHTML = "";
        if (!foodItems.length) {
            const empty = document.createElement("div");
            empty.className = "food-menu-empty";
            empty.textContent = "По этому фильтру ничего не найдено.";
            grid.appendChild(empty);
            return;
        }
        const fragment = document.createDocumentFragment();
        foodItems.forEach(item => fragment.appendChild(makeFoodCard(item)));
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

                const top = document.createElement("div");
                top.className = "food-cart-row-top";

                const name = document.createElement("div");
                name.className = "food-cart-row-name";
                name.textContent = item.name || "Позиция";

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
    let foodOrderBusy = false;
    let foodCheckoutBusy = false;
    let foodOrderPage = 1;

    function foodMessage(message) {
        const node = document.getElementById("foodOrderMessage");
        if (node) node.textContent = message || "";
    }

    function resetFoodOrder() {
        currentFoodOrderId = null;
        currentFoodOrderSaved = false;
        ["foodOrderTable", "foodOrderGuest", "foodOrderNote"].forEach(id => {
            const element = document.getElementById(id);
            if (element) element.value = "";
        });
        foodMessage("");
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
                    cart: getCart()
                })
            });
            const data = await response.json();
            if (!response.ok || !data.success) throw new Error(data.message || "Не удалось сохранить заказ");
            currentFoodOrderId = data.order.id;
            currentFoodOrderSaved = true;
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

    async function createFoodPrecheck() {
        if (foodCheckoutBusy) return;
        if (!getCart().length) { foodMessage("Добавьте блюдо в заказ"); return; }
        foodCheckoutBusy = true;
        const button = document.getElementById("foodPrecheckCheckout");
        if (button) button.disabled = true;
        try {
            // Always save the freshest cart before opening the precheck.
            const saved = await saveFoodOrder();
            if (saved) {
                foodMessage("Заказ №" + saved.id + " сохранён · ожидает оплаты");
                openFoodTicket(saved.id, "precheck");
            }
        } finally {
            foodCheckoutBusy = false;
            if (button) button.disabled = false;
        }
    }

    async function payExistingFoodOrder() {
        if (foodCheckoutBusy || !getCart().length) return;
        foodCheckoutBusy = true;
        const button = document.getElementById("foodCompletePayment");
        if (button) button.disabled = true;
        try {
            const order = await saveFoodOrder();
            if (!order) return;
            // Only /sales/pay records real sales, recipe stock movements and reKassa.
            const card = Number(String(document.getElementById("cardInput")?.value || "").replace(",", ".")) || 0;
            const kaspi = Number(String(document.getElementById("kaspiInput")?.value || "").replace(",", ".")) || 0;
            if (card > 0 || kaspi > 0) pay();
            else openCashChangeModal();
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
        for (const id of ["cashInput","cardInput","kaspiInput"]) {
            const input = document.getElementById(id);
            if (input) input.value = "";
        }
        foodMessage("Новый заказ");
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
    function openFoodTicket(orderId, kind) {
        if (!orderId) { foodMessage("Сначала сохраните заказ"); return; }
        const modal = document.getElementById("foodTicketModal");
        const frame = document.getElementById("foodTicketFrame");
        if (!modal || !frame) return;
        document.getElementById("foodTicketHeading").textContent = kind === "kitchen" ? "Заказ на кухню" : "Пречек гостю";
        frame.src = "/food/orders/" + encodeURIComponent(orderId) + "/ticket/" + kind + "?embed=1";
        modal.hidden = false;
    }
    function closeFoodTicket() {
        const modal = document.getElementById("foodTicketModal");
        if (modal) modal.hidden = true;
        const frame = document.getElementById("foodTicketFrame");
        if (frame) frame.src = "about:blank";
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
            document.getElementById("foodOrderTable").value = data.order.table_name || "";
            document.getElementById("foodOrderGuest").value = data.order.guest_name || "";
            document.getElementById("foodOrderNote").value = data.order.note || "";
            if (typeof switchSalesTab === "function") switchSalesTab("cart");
            foodMessage("Открыт заказ №" + currentFoodOrderId);
        } catch (error) {
            foodMessage(error.message || "Не удалось открыть заказ");
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
        for (const order of data.orders || []) {
            const row = document.createElement("div");
            row.className = "food-history-row";
            const label = document.createElement("div");
            const title = document.createElement("strong");
            title.textContent = "№" + order.id + " · " + (order.table_name || "Без стола");
            const detail = document.createElement("small");
            detail.textContent = (order.status === "paid" ? "Оплачен в Nika" : order.status === "external_paid" ? "Чек внешней ККМ №" + (order.external_receipt_number || "—") + " · без списания склада" : order.status === "cancelled" ? "Отменён" : "Ожидает оплаты") +
                " · " + money(order.total_amount) + " · " + (order.created_at_display || order.created_at.slice(0, 16).replace("T", " "));
            label.append(title, detail);
            const buttons = document.createElement("div");
            if (order.status === "open") {
                const open = document.createElement("button");
                open.textContent = "Открыть";
                open.addEventListener("click", () => openFoodOrder(order.id));
                buttons.appendChild(open);
            }
            for (const [kind, caption] of [["kitchen","Кухня"],["precheck","Пречек"]]) {
                const print = document.createElement("button");
                print.textContent = caption;
                print.addEventListener("click", () => openFoodTicket(order.id, kind));
                buttons.appendChild(print);
            }
            row.append(label,buttons);
            list.appendChild(row);
        }
        foodOrderPage += 1;
        const more = document.getElementById("foodOrderHistoryMore");
        if (more) more.hidden = !data.has_more;
    }

    function initFoodOrderControls() {
        if (!["foodservice", "universal"].includes(window.NIKA_BUSINESS_MODE)) return;
        document.getElementById("foodOrderSave")?.addEventListener("click", saveFoodOrder);
        document.getElementById("foodOrderNew")?.addEventListener("click", newFoodOrder);
        document.getElementById("foodPrecheckCheckout")?.addEventListener("click", createFoodPrecheck);
        document.getElementById("foodCompletePayment")?.addEventListener("click", payExistingFoodOrder);
        document.getElementById("foodExternalPayment")?.addEventListener("click", openExternalPayment);
        document.getElementById("foodExternalConfirm")?.addEventListener("click", confirmExternalPayment);
        document.querySelectorAll("[data-food-external-close]").forEach(el => el.addEventListener("click", () => setExternalModal(false)));
        document.getElementById("foodOrderKitchen")?.addEventListener("click", () => printFoodTicket("kitchen"));
        document.getElementById("foodOrderPrecheck")?.addEventListener("click", () => printFoodTicket("precheck"));
        document.getElementById("foodOrderDetails")?.addEventListener("click", () => setFoodDetails(true));
        document.querySelectorAll("[data-food-details-close]").forEach(el => el.addEventListener("click", () => setFoodDetails(false)));
        document.querySelectorAll("[data-food-ticket-close]").forEach(el => el.addEventListener("click", closeFoodTicket));
        document.getElementById("foodTicketPrint")?.addEventListener("click", () => {
            document.getElementById("foodTicketFrame")?.contentWindow?.print();
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
        clearOrder: resetFoodOrder
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initFoodSalesMode, { once: true });
    } else {
        initFoodSalesMode();
    }
})();