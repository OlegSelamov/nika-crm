(() => {
    const MODE_KEY = "nika_sales_mode";
    const MAX_MENU_PAGES = 10;
    const PAGE_SIZE = 100;

    let foodItems = [];
    let foodCategory = "all";
    let foodLoaded = false;
    let foodLoading = false;

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

    async function fetchFoodItemsPage(page) {
        const response = await fetch(
            `/api/catalog/items?type=dish&limit=${PAGE_SIZE}&page=${page}`
        );
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        return response.json();
    }

    async function loadFoodMenu() {
        if (foodLoaded || foodLoading) {
            if (foodLoaded) renderFoodMenu();
            return;
        }

        foodLoading = true;
        const grid = document.getElementById("foodMenuGrid");
        if (grid) {
            grid.innerHTML = '<div class="food-menu-loading">Загружаем меню…</div>';
        }

        try {
            const loaded = [];
            let page = 1;
            let hasMore = true;

            while (hasMore && page <= MAX_MENU_PAGES) {
                const data = await fetchFoodItemsPage(page);
                const pageItems = Array.isArray(data.items) ? data.items : [];
                loaded.push(...pageItems);
                hasMore = Boolean(data.has_more);
                page += 1;
            }

            foodItems = loaded;
            foodLoaded = true;
            renderFoodCategories();
            renderFoodMenu();
        } catch (error) {
            console.error("FOOD MENU LOAD ERROR:", error);
            if (grid) {
                grid.innerHTML = '<div class="food-menu-empty">Не удалось загрузить каталог. Обновите страницу или проверьте соединение.</div>';
            }
        } finally {
            foodLoading = false;
        }
    }

    function itemCategory(item) {
        return String(item?.category || "").trim() || "Без категории";
    }

    function renderFoodCategories() {
        const root = document.getElementById("foodCategories");
        if (!root) return;

        const categories = Array.from(new Set(foodItems.map(itemCategory)))
            .sort((a, b) => a.localeCompare(b, "ru"));

        root.innerHTML = "";

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
    }

    function selectFoodCategory(category) {
        foodCategory = category || "all";
        updateCategoryButtons();
        renderFoodMenu();
    }

    function updateCategoryButtons() {
        document.querySelectorAll(".food-category-btn").forEach(button => {
            button.classList.toggle("active", button.dataset.category === foodCategory);
        });
    }

    function foodQuery() {
        return String(document.getElementById("foodSearch")?.value || "")
            .trim()
            .toLowerCase();
    }

    function filteredFoodItems() {
        const query = foodQuery();

        return foodItems.filter(item => {
            if (foodCategory !== "all" && itemCategory(item) !== foodCategory) {
                return false;
            }

            if (!query) return true;

            const haystack = [
                item.name,
                item.category,
                item.barcode,
                item.gtin,
                item.ntin
            ].map(value => String(value || "").toLowerCase()).join(" ");

            return haystack.includes(query);
        });
    }

    function menuInitial(name) {
        const value = String(name || "").trim();
        return value ? value[0].toUpperCase() : "N";
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

        button.addEventListener("click", () => {
            if (typeof selectItemForSale !== "function") return;
            selectItemForSale(
                Number(item.id),
                item.name || "Блюдо",
                Number(item.retail_price || 0),
                item.unit || "шт",
                item.gtin || "",
                item.ntin || ""
            );
            renderFoodCart();
        });

        return button;
    }

    function renderFoodMenu() {
        const grid = document.getElementById("foodMenuGrid");
        if (!grid || !foodLoaded) return;

        const items = filteredFoodItems();
        grid.innerHTML = "";

        if (!items.length) {
            const empty = document.createElement("div");
            empty.className = "food-menu-empty";
            empty.textContent = foodItems.length
                ? "По этому фильтру ничего не найдено."
                : "В каталоге пока нет товаров. Добавьте блюда в разделе «Каталог».";
            grid.appendChild(empty);
            return;
        }

        items.forEach(item => grid.appendChild(makeFoodCard(item)));
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

    function initFoodSalesMode() {
        document.getElementById("salesModeRetail")?.addEventListener("click", () => setMode("retail"));
        document.getElementById("salesModeFood")?.addEventListener("click", () => setMode("food"));
        document.getElementById("foodSearch")?.addEventListener("input", renderFoodMenu);
        document.getElementById("foodClearCart")?.addEventListener("click", clearFoodCart);
        document.getElementById("foodClientButton")?.addEventListener("click", () => {
            if (typeof openClientSheet === "function") openClientSheet();
        });

        hookSharedCartRenderer();
        setMode(currentMode());
        renderFoodCart();

        window.addEventListener("nika:sale-completed", renderFoodCart);
    }

    window.NikaFoodSales = {
        setMode,
        reloadMenu: () => {
            foodLoaded = false;
            foodItems = [];
            return loadFoodMenu();
        },
        renderCart: renderFoodCart
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initFoodSalesMode, { once: true });
    } else {
        initFoodSalesMode();
    }
})();