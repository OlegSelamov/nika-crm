(() => {
    const MODE_KEY = "nika_sales_mode";
    const PAGE_SIZE = 36;
    let foodItems = [];
    let foodCategory = "all";
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
            foodCategoryNames = (data.categories || []).map(row => row.name);
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
                type: "food_menu",
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

    function renderFoodCategories() {
        const root = document.getElementById("foodCategories");
        if (!root) return;

        const categories = Array.from(new Set(foodCategoryNames))
            .sort((a, b) => a.localeCompare(b, "ru"));

        root.innerHTML = "";
        const count = document.getElementById("foodCategoryCount");
        if (count) count.textContent = String(categories.length);

        const allButton = document.createElement("button");
        allButton.type = "button";
        allButton.className = "food-category-btn";
        allButton.dataset.category = "all";
        allButton.textContent = "Все";
        allButton.addEventListener("click", () => selectFoodCategory("all"));
        root.appendChild(allButton);

        categories.forEach(category => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "food-category-btn";
            button.dataset.category = category;
            button.textContent = category;
            button.addEventListener("click", () => selectFoodCategory(category));
            root.appendChild(button);
        });

        updateCategoryButtons();
        filterFoodCategories();
    }

    function selectFoodCategory(category) {
        foodCategory = category || "all";
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
        if (selected) selected.textContent = foodCategory === "all" ? "Все категории" : foodCategory;
    }

    function menuInitial(name) {
        const value = String(name || "").trim();
        return value ? value[0].toUpperCase() : "N";
    }

    let pendingModifierItem = null;
    let pendingModifierGroups = [];

    async function addFoodItem(item) {
        if ((item.item_type || "product") === "product") {
            selectItemForSale(Number(item.id), item.name || "Товар", Number(item.retail_price || 0), item.unit || "шт", item.gtin || "", item.ntin || "");
            renderFoodCart();
            return;
        }
        try {
            const response = await fetch('/api/items/' + encodeURIComponent(item.id) + '/modifiers', {headers:{Accept:'application/json'}});
            const data = response.ok ? await response.json() : null;
            if (data && data.success && Array.isArray(data.groups) && data.groups.length) {
                openFoodModifierModal(item, data.groups);
                return;
            }
        } catch (error) { console.error('MODIFIER LOAD ERROR:', error); }
        selectItemForSale(Number(item.id), item.name || 'Блюдо', Number(item.retail_price || 0), item.unit || 'шт', item.gtin || '', item.ntin || '');
        renderFoodCart();
    }

    function openFoodModifierModal(item, groups) {
        pendingModifierItem=item; pendingModifierGroups=groups;
        const modal=document.getElementById('foodModifierModal'), root=document.getElementById('foodModifierGroups');
        document.getElementById('foodModifierTitle').textContent=item.name || 'Блюдо';
        root.innerHTML='';
        groups.forEach(group=>{
            const section=document.createElement('section'); section.className='food-modifier-group';
            section.innerHTML='<div class="food-modifier-group-title"><strong>'+escapeFood(group.name)+'</strong><small>'+(group.min_select>0?'Выберите обязательно':'По желанию')+(group.max_select>1?' · до '+group.max_select:'')+'</small></div>';
            (group.options||[]).forEach(option=>{
                const label=document.createElement('label'); label.className='food-modifier-option';
                const input=document.createElement('input'); input.type='checkbox'; input.name='food-modifier-'+group.id; input.value=option.id; input.dataset.groupId=group.id;
                input.addEventListener('change',()=>{const checked=section.querySelectorAll('input:checked');const max=Number(group.max_select||0);if(max>0&&checked.length>max){input.checked=false;return;} renderFoodModifierTotal();});
                const text=document.createElement('span'); text.innerHTML='<b>'+escapeFood(option.name)+'</b>'+(Number(option.price_delta)?'<small>+'+money(option.price_delta)+'</small>':'');
                label.append(input,text); section.appendChild(label);
            }); root.appendChild(section);
        });
        modal.hidden=false; renderFoodModifierTotal();
    }
    function escapeFood(v){const d=document.createElement('div');d.textContent=String(v||'');return d.innerHTML;}
    function selectedFoodModifiers(){const selected=[];document.querySelectorAll('#foodModifierGroups input:checked').forEach(input=>{const g=pendingModifierGroups.find(x=>String(x.id)===String(input.dataset.groupId));const o=g?.options?.find(x=>String(x.id)===String(input.value));if(o)selected.push(o)});return selected}
    function renderFoodModifierTotal(){const extra=selectedFoodModifiers().reduce((s,o)=>s+Number(o.price_delta||0),0);const total=Number(pendingModifierItem?.retail_price||0)+extra;const n=document.getElementById('foodModifierTotal');if(n)n.textContent=money(total)}
    function closeFoodModifierModal(){const m=document.getElementById('foodModifierModal');if(m)m.hidden=true;pendingModifierItem=null;pendingModifierGroups=[]}
    function confirmFoodModifiers(){
        if(!pendingModifierItem)return;
        for(const group of pendingModifierGroups){const count=document.querySelectorAll('#foodModifierGroups input[data-group-id="'+group.id+'"]:checked').length;if(count<Number(group.min_select||0)){alert('Выберите: '+group.name);return}}
        const mods=selectedFoodModifiers(); const price=Number(pendingModifierItem.retail_price||0)+mods.reduce((s,o)=>s+Number(o.price_delta||0),0);
        cart.push({id:Number(pendingModifierItem.id),name:pendingModifierItem.name||'Блюдо',price:price,qty:1,gtin:pendingModifierItem.gtin||'',ntin:pendingModifierItem.ntin||'',unit:pendingModifierItem.unit||'шт',item_type:'dish',modifiers:mods.map(o=>({id:o.id,name:o.name,price_delta:Number(o.price_delta||0)}))});
        closeFoodModifierModal(); renderCart(); renderFoodCart();
    }

    function makeFoodCard(item) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "food-menu-card";

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

        const info = document.createElement("div");
        info.className = "food-menu-info";

        const name = document.createElement("div");
        name.className = "food-menu-name";
        name.textContent = item.name || "Без названия";

        const price = document.createElement("div");
        price.className = "food-menu-price";
        price.textContent = money(item.retail_price);

        info.append(name, price);
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


    let currentFoodOrderId = null;
    let currentFoodOrderSaved = false;
    let foodOrderBusy = false;
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
            detail.textContent = (order.status === "paid" ? "Оплачен" : order.status === "cancelled" ? "Отменён" : "Открыт") +
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
        if (window.NIKA_BUSINESS_MODE !== "foodservice") return;
        document.getElementById("foodOrderSave")?.addEventListener("click", saveFoodOrder);
        document.getElementById("foodOrderKitchen")?.addEventListener("click", () => printFoodTicket("kitchen"));
        document.getElementById("foodOrderPrecheck")?.addEventListener("click", () => printFoodTicket("precheck"));
        document.getElementById("foodOrderDetails")?.addEventListener("click", () => setFoodDetails(true));
        document.querySelectorAll("[data-food-details-close]").forEach(el => el.addEventListener("click", () => setFoodDetails(false)));
        document.querySelectorAll("[data-food-ticket-close]").forEach(el => el.addEventListener("click", closeFoodTicket));
        document.getElementById("foodTicketPrint")?.addEventListener("click", () => {
            document.getElementById("foodTicketFrame")?.contentWindow?.print();
        });
        document.addEventListener("keydown", event => {
            if (event.key === "Escape") { setFoodDetails(false); closeFoodTicket(); }
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
        getSavedOrderId: () => currentFoodOrderSaved ? currentFoodOrderId : null,
        clearOrder: resetFoodOrder
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initFoodSalesMode, { once: true });
    } else {
        initFoodSalesMode();
    }
})();