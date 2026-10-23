/* Retail carts are drafts, never sales. Keep them isolated from Food POS. */
(() => {
    "use strict";
    const owner = window.NIKA_RETAIL_DRAFT_OWNER || [];
    if (!owner[0] || !owner[1]) return;
    const storageKey = "nika:retail:cart:v3:" + owner[0] + ":" + owner[1];
    const api = "/api/sales/cart-drafts";
    let started = false, ready = false, suspended = false;
    let autoTimer = null, pendingWrite = Promise.resolve();
    let currentManualId = null, knownDrafts = [];
    let serverAvailable = false;

    const el = id => document.getElementById(id);
    const active = () => window.NIKA_BUSINESS_MODE !== "foodservice" &&
        !document.body.classList.contains("food-sales-mode");
    const getCart = () => Array.isArray(cart) ? cart : [];
    const snapshot = () => ({
        cart: getCart().map(row => ({...row})),
        client_id: selectedClient || null,
        client_name: el("clientSearch")?.value || "",
        updated_at: Date.now()
    });
    const localRead = () => {
        try { return JSON.parse(localStorage.getItem(storageKey) || "null"); }
        catch (_) { return null; }
    };
    const localWrite = value => {
        try { localStorage.setItem(storageKey, JSON.stringify(value)); }
        catch (_) { /* browser storage may be disabled */ }
    };
    const notice = (message, bad = false) => {
        const node = el("retailDraftStatus");
        if (!node) return;
        node.textContent = message;
        node.classList.toggle("is-error", bad);
    };
    const jsonRequest = async (url, opts) => {
        const response = await fetch(url, {credentials:"same-origin", ...(opts || {})});
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.success === false) {
            throw new Error(data.error || data.message || "Не удалось связаться с сервером");
        }
        return data;
    };
    const postDraft = (payload) => jsonRequest(api, {
        method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify(payload)
    });
    const queueWrite = fn => {
        // A slow autosave may finish after payment. Serialize POST and DELETE
        // so an earlier request never resurrects a completed basket.
        const next = pendingWrite.catch(() => {}).then(fn);
        pendingWrite = next.catch(() => {});
        return next;
    };
    const syncAuto = (state) => queueWrite(async () => {
        if (state.cart.length) {
            await postDraft({...state, is_auto:true});
        } else {
            await jsonRequest(api + "/active", {method:"DELETE"});
        }
    });
    const schedule = () => {
        if (!ready || suspended || !active()) return;
        clearTimeout(autoTimer);
        const state = snapshot();
        localWrite(state);
        autoTimer = setTimeout(() => {
            if (!active()) return;
            void syncAuto(state).catch(() => {
                // The local, company/user-scoped copy remains recoverable.
                notice("Корзина сохранена на устройстве · нет связи с сервером", true);
            });
        }, 850);
    };

    function apply(state, manualId = null) {
        if (!state || !Array.isArray(state.cart)) return;
        suspended = true;
        try {
            cart = state.cart.filter(x => x && Number(x.id) > 0 &&
                Number(x.qty) > 0 && Number(x.price) >= 0)
                .map(x => ({...x}));
            const clientId = Number(state.client_id) || null;
            selectedClient = clientId;
            selectedClientData = clientId ? {id:clientId, full_name:state.client_name || "Клиент"} : null;
            if (el("clientSearch")) el("clientSearch").value = state.client_name || (clientId ? "Клиент" : "");
            if (el("cashInput")) el("cashInput").value = "";
            if (el("cardInput")) el("cardInput").value = "";
            if (el("kaspiInput")) el("kaspiInput").value = "";
            currentManualId = manualId;
            renderCart();
        } finally {
            suspended = false;
        }
        localWrite(snapshot());
        if (ready) schedule();
    }

    async function listDrafts() {
        const data = await jsonRequest(api);
        serverAvailable = true;
        knownDrafts = data.drafts || [];
        if (el("retailDraftCount")) {
            const count = knownDrafts.filter(d => !d.is_auto).length;
            el("retailDraftCount").textContent = count ? "· " + count : "";
        }
        renderDraftList();
        return knownDrafts;
    }

    function renderDraftList() {
        const root = el("retailDraftList");
        if (!root) return;
        root.replaceChildren();
        if (!knownDrafts.length) {
            const empty = document.createElement("span");
            empty.textContent = "Сохранённых корзин пока нет.";
            root.appendChild(empty);
            return;
        }
        knownDrafts.forEach(draft => {
            const row = document.createElement("div");
            row.className = "retail-draft-row";
            const label = document.createElement("div");
            const title = document.createElement("strong");
            title.textContent = draft.is_auto ? "Текущая корзина (автосохранение)" : draft.title;
            const meta = document.createElement("small");
            const time = draft.updated_at ? new Date(draft.updated_at).toLocaleString("ru-RU") : "";
            meta.textContent = (draft.items_count || 0) + " поз. · " + time;
            label.append(title, meta);
            const buttons = document.createElement("div");
            buttons.className = "retail-draft-row__actions";
            const resume = document.createElement("button");
            resume.type = "button"; resume.textContent = "Продолжить";
            resume.addEventListener("click", () => void resumeDraft(draft.id, resume));
            const remove = document.createElement("button");
            remove.type = "button"; remove.textContent = "Удалить";
            remove.className = "retail-draft-delete";
            remove.addEventListener("click", () => void deleteDraft(draft.id, remove));
            buttons.append(resume, remove);
            row.append(label, buttons);
            root.appendChild(row);
        });
    }
    async function resumeDraft(id, button) {
        if (!active()) return;
        if (getCart().length && !window.confirm("Заменить текущую корзину? Если её нужно сохранить отдельно, сначала нажмите «Сохранить корзину».")) return;
        button.disabled = true;
        try {
            const data = await jsonRequest(api + "/" + encodeURIComponent(id));
            apply({
                ...data.draft,
                client_name: data.draft.client_name || ""
            }, data.draft.is_auto ? null : data.draft.id);
            switchSalesTab("cart");
            notice("Корзина восстановлена. Проверьте позиции перед оплатой.");
            schedule();
        } catch (error) { notice(error.message, true); }
        finally { button.disabled = false; }
    }
    async function deleteDraft(id, button) {
        if (!window.confirm("Удалить сохранённую корзину?")) return;
        button.disabled = true;
        try {
            await jsonRequest(api + "/" + encodeURIComponent(id), {method:"DELETE"});
            if (currentManualId === id) currentManualId = null;
            await listDrafts();
            notice("Корзина удалена");
        } catch (error) { notice(error.message, true); button.disabled = false; }
    }
    async function saveManually() {
        if (!active()) return;
        if (!getCart().length) { notice("Добавьте товары в корзину перед сохранением.", true); return; }
        const button = el("retailSaveCart");
        if (button) button.disabled = true;
        try {
            const state = snapshot();
            const title = currentManualId
                ? knownDrafts.find(d => d.id === currentManualId)?.title || "Сохранённая корзина"
                : "Корзина · " + new Date().toLocaleString("ru-RU", {day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit"});
            const response = await postDraft({
                ...state, id: currentManualId, is_auto:false, title
            });
            currentManualId = response.id;
            await listDrafts();
            notice("Корзина сохранена. Её можно открыть из истории продаж.");
            schedule();
        } catch (error) { notice(error.message || "Не удалось сохранить", true); }
        finally { if (button) button.disabled = false; }
    }
    async function repeatSale(id, button) {
        if (!active()) return;
        if (getCart().length &&
            !window.confirm("Заменить текущую корзину? Сначала сохраните её, если хотите вернуться к ней позже.")) return;
        if (button) button.disabled = true;
        try {
            const result = await jsonRequest("/api/sales/" + encodeURIComponent(id) + "/repeat-cart");
            if (!result.cart?.length) {
                throw new Error(result.skipped?.join("; ") || "Нет позиций для повторной продажи");
            }
            if (result.skipped?.length &&
                !window.confirm("Не перенесены:\n" + result.skipped.join("\n") +
                    "\n\nПродолжить без этих позиций?")) return;
            currentManualId = null;
            apply({
                cart:result.cart,client_id:result.client_id,
                client_name:result.client_name
            });
            switchSalesTab("cart");
            notice("Создана новая корзина по продаже №" + id +
                ". Исходный чек не изменён. Проверьте товары и цены.");
            schedule();
        } catch (error) { notice(error.message, true); window.alert(error.message); }
        finally { if (button) button.disabled = false; }
    }
    window.retailRepeatSale = (id, button) => void repeatSale(id, button);

    async function start() {
        if (started) return;
        started = true;
        const originalRender = window.renderCart;
        if (typeof originalRender === "function") {
            window.renderCart = function(...args) {
                const value = originalRender.apply(this, args);
                schedule();
                return value;
            };
        }
        for (const name of ["confirmClient", "selectDefaultPrivateClient"]) {
            const original = window[name];
            if (typeof original !== "function") continue;
            window[name] = function(...args) {
                const result = original.apply(this, args);
                Promise.resolve(result).then(() => schedule()).catch(() => {});
                return result;
            };
        }
        el("retailSaveCart")?.addEventListener("click", () => void saveManually());
        el("retailOpenDrafts")?.addEventListener("click", () => {
            if (!active()) return;
            switchSalesTab("history");
            void listDrafts().catch(error => notice(error.message, true));
        });
        el("retailDraftRefresh")?.addEventListener("click", () =>
            void listDrafts().catch(error => notice(error.message, true)));
        const local = localRead();
        try {
            const list = await listDrafts();
            if (!getCart().length && active()) {
                const auto = list.find(d => d.is_auto);
                if (auto) {
                    const data = await jsonRequest(api + "/" + auto.id);
                    const server = data.draft;
                    const serverTime = new Date(server.updated_at).getTime();
                    if (local && local.updated_at > serverTime) apply(local);
                    else apply(server);
                } else if (local && Array.isArray(local.cart) && local.cart.length) {
                    apply(local);
                }
            }
        } catch (_) {
            if (!getCart().length && active() && local?.cart?.length) apply(local);
            notice("Сервер временно недоступен. Корзина хранится на устройстве.", true);
        }
        ready = true;
        if (getCart().length && active()) {
            notice("Предыдущая корзина восстановлена. Проверьте товары и клиента.");
            schedule();
        }
    }
    window.addEventListener("nika:sale-completed", () => {
        if (!active()) return;
        clearTimeout(autoTimer);
        const consumedId = currentManualId;
        currentManualId = null;
        localWrite({cart:[],client_id:null,client_name:"",updated_at:Date.now()});
        void queueWrite(async () => {
            await jsonRequest(api + "/active", {method:"DELETE"});
            if (consumedId) await jsonRequest(api + "/" + consumedId, {method:"DELETE"});
            await listDrafts();
        }).catch(() => { /* A cleared local snapshot prevents accidental restoration. */ });
    });

    // Existing sales.js initializes storefront carts in its load handler.
    // Running afterward prevents a restored draft from overwriting an import.
    window.addEventListener("load", () => { void start(); });
})();