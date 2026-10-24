/* Manually parked retail baskets. No automatic saving or restoration.
   Retail drafts are not sales, do not reserve stock and do not affect Food POS. */
(() => {
    "use strict";
    const owner = window.NIKA_RETAIL_DRAFT_OWNER || [];
    if (!owner[0] || !owner[1]) return;

    const api = "/api/sales/cart-drafts";
    let started = false;
    let currentManualId = null;
    let oldAutoId = null;
    let knownDrafts = [];
    let noticeTimer = null;
    let saleSequence = 0;
    let restoring = false;
    let pendingWrite = Promise.resolve();

    const el = id => document.getElementById(id);
    const active = () => window.NIKA_BUSINESS_MODE !== "foodservice" &&
        !document.body.classList.contains("food-sales-mode");
    const getCart = () => Array.isArray(cart) ? cart : [];
    const snapshot = () => ({
        cart: getCart().map(row => ({...row})),
        client_id: selectedClient || null,
        client_name: el("clientSearch")?.value || ""
    });

    const notice = (message, bad = false) => {
        const node = el("retailDraftStatus");
        if (!node) return;
        clearTimeout(noticeTimer);
        node.textContent = message;
        node.classList.toggle("is-error", bad);
        node.classList.toggle("is-visible", Boolean(message));
        noticeTimer = setTimeout(() => {
            node.classList.remove("is-visible");
            node.textContent = "";
        }, bad ? 6500 : 4000);
    };
    const jsonRequest = async (url, opts) => {
        const response = await fetch(url, {credentials:"same-origin", ...(opts || {})});
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.success === false) {
            throw new Error(data.error || data.message || "Не удалось связаться с сервером");
        }
        return data;
    };
    const postDraft = payload => jsonRequest(api, {
        method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify(payload)
    });
    const queueWrite = fn => {
        // Deletion after successful payment must not race a manual save.
        const next = pendingWrite.catch(() => {}).then(fn);
        pendingWrite = next.catch(() => {});
        return next;
    };

    function clearCheckoutAfterSave() {
        cart = [];
        currentManualId = null;
        oldAutoId = null;
        renderCart();
        if (typeof resetSaleAmounts === "function") resetSaleAmounts();
        selectedClient = null;
        selectedClientData = null;
        if (el("clientSearch")) el("clientSearch").value = "";
        if (el("search")) el("search").value = "";
        if (el("itemsList")) el("itemsList").style.display = "none";
        // Standard default for the NEXT sale. This does not affect the saved
        // snapshot; the saved client stays with the parked basket.
        if (typeof selectDefaultPrivateClient === "function") {
            void selectDefaultPrivateClient();
        }
    }

    function apply(state, manualId = null, previousAutoId = null) {
        if (!state || !Array.isArray(state.cart)) return;
        restoring = true;
        try {
            cart = state.cart.filter(x => x && Number(x.id) > 0 &&
                Number(x.qty) > 0 && Number(x.price) >= 0)
                .map(x => ({...x}));
            const clientId = Number(state.client_id) || null;
            selectedClient = clientId;
            selectedClientData = clientId
                ? {id:clientId, full_name:state.client_name || "Клиент"}
                : null;
            if (el("clientSearch")) {
                el("clientSearch").value = state.client_name || (clientId ? "Клиент" : "");
            }
            if (typeof resetSaleAmounts === "function") resetSaleAmounts();
            currentManualId = manualId;
            oldAutoId = previousAutoId;
            renderCart();
        } finally {
            restoring = false;
        }
    }

    async function listDrafts() {
        const data = await jsonRequest(api);
        knownDrafts = Array.isArray(data.drafts) ? data.drafts : [];
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
            title.textContent = draft.is_auto
                ? "Старая автокорзина (можно восстановить или удалить)"
                : (draft.title || "Сохранённая корзина");
            const meta = document.createElement("small");
            const parsed = draft.updated_at ? new Date(draft.updated_at) : null;
            const time = parsed && !Number.isNaN(parsed.getTime())
                ? parsed.toLocaleString("ru-RU") : "";
            meta.textContent = (draft.items_count || 0) + " поз. · " + time;
            label.append(title, meta);
            const actions = document.createElement("div");
            actions.className = "retail-draft-row__actions";
            const resume = document.createElement("button");
            resume.type = "button";
            resume.textContent = "Продолжить";
            resume.addEventListener("click", () => void resumeDraft(draft.id, resume));
            const remove = document.createElement("button");
            remove.type = "button";
            remove.textContent = "Удалить";
            remove.className = "retail-draft-delete";
            remove.addEventListener("click", () => void deleteDraft(draft.id, remove));
            actions.append(resume, remove);
            row.append(label, actions);
            root.appendChild(row);
        });
    }

    async function resumeDraft(id, button) {
        if (!active()) return;
        if (getCart().length &&
            !window.confirm("Заменить текущую корзину? Сначала сохраните её, если хотите вернуться к ней позже.")) return;
        button.disabled = true;
        try {
            const data = await jsonRequest(api + "/" + encodeURIComponent(id));
            apply(data.draft, data.draft.is_auto ? null : data.draft.id,
                data.draft.is_auto ? data.draft.id : null);
            switchSalesTab("cart");
            notice("Корзина открыта. Проверьте позиции перед оплатой.");
        } catch (error) { notice(error.message, true); }
        finally { button.disabled = false; }
    }

    async function deleteDraft(id, button) {
        if (!window.confirm("Удалить сохранённую корзину?")) return;
        button.disabled = true;
        try {
            await queueWrite(() => jsonRequest(api + "/" + encodeURIComponent(id), {
                method:"DELETE"
            }));
            if (currentManualId === id) currentManualId = null;
            if (oldAutoId === id) oldAutoId = null;
            await listDrafts();
            notice("Корзина удалена.");
        } catch (error) { notice(error.message, true); button.disabled = false; }
    }

    async function saveManually() {
        if (!active()) return;
        if ((typeof salePaymentBusy !== "undefined" && salePaymentBusy) ||
            (typeof invoiceCreationBusy !== "undefined" && invoiceCreationBusy)) {
            notice("Дождитесь завершения оплаты или создания счёта.", true);
            return;
        }
        if (!getCart().length) {
            notice("Добавьте товары в корзину перед сохранением.", true);
            return;
        }
        const button = el("retailSaveCart");
        if (button?.disabled) return;
        if (button) button.disabled = true;
        const state = snapshot();
        const stateKey = JSON.stringify(state);
        const sequenceAtSave = saleSequence;
        const manualIdAtSave = currentManualId;
        const legacyIdAtSave = oldAutoId;
        const title = manualIdAtSave
            ? knownDrafts.find(d => d.id === manualIdAtSave)?.title || "Сохранённая корзина"
            : "Корзина · " + new Date().toLocaleString("ru-RU", {
                day:"2-digit", month:"2-digit", hour:"2-digit", minute:"2-digit"
            });

        try {
            // Only an explicit click creates or updates a cart on the server.
            const response = await queueWrite(() => postDraft({
                ...state, id:manualIdAtSave, is_auto:false, title
            }));

            if (saleSequence !== sequenceAtSave) {
                // Payment completed during the network request: don't park a
                // completed transaction as an outstanding sale.
                await queueWrite(() => jsonRequest(api + "/" + response.id, {method:"DELETE"}));
                return;
            }
            if (legacyIdAtSave) {
                // The old automatic record is converted to a manual one
                // only after the new record has been committed successfully.
                await queueWrite(() => jsonRequest(api + "/" + legacyIdAtSave, {
                    method:"DELETE"
                })).catch(() => {});
            }
            if (stateKey === JSON.stringify(snapshot())) {
                // Parking the basket immediately frees the register for
                // the next sale. Never clear it if server saving failed.
                clearCheckoutAfterSave();
                notice("Корзина сохранена в истории. Можно оформлять новую продажу.");
            } else {
                // The operator changed the cart while the POST was in flight.
                // Keep those changes instead of silently discarding them.
                currentManualId = null;
                oldAutoId = null;
                notice("Корзина сохранена, но новые изменения оставлены на кассе.", true);
            }
            void listDrafts().catch(() => {});
        } catch (error) {
            notice(error.message || "Не удалось сохранить корзину. Она осталась на кассе.", true);
        } finally {
            if (button) button.disabled = false;
        }
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
            apply({
                cart:result.cart, client_id:result.client_id,
                client_name:result.client_name
            });
            switchSalesTab("cart");
            notice("Создана новая корзина по продаже №" + id +
                ". Исходный чек не изменён. Проверьте товары и цены.");
        } catch (error) { notice(error.message, true); window.alert(error.message); }
        finally { if (button) button.disabled = false; }
    }
    window.retailRepeatSale = (id, button) => void repeatSale(id, button);

    function start() {
        if (started) return;
        started = true;
        // Do not restore any old localStorage copy or server auto draft here.
        // New visits to POS must always allow a genuinely new transaction.
        // We only observe an emptied cart to detach an old manual draft after
        // the cashier removes all positions, without changing retail checkout.
        const originalRender = window.renderCart;
        if (typeof originalRender === "function") {
            window.renderCart = function(...args) {
                const value = originalRender.apply(this, args);
                const paymentInProgress =
                    (typeof salePaymentBusy !== "undefined" && salePaymentBusy) ||
                    (typeof invoiceCreationBusy !== "undefined" && invoiceCreationBusy);
                if (!restoring && !paymentInProgress && !getCart().length) {
                    currentManualId = null;
                    oldAutoId = null;
                }
                return value;
            };
        }
        el("retailSaveCart")?.addEventListener("click", () => void saveManually());
        el("retailDraftRefresh")?.addEventListener("click", () =>
            void listDrafts().catch(error => notice(error.message, true)));
        // Saved drafts load on demand, only when the cashier opens history.
        el("historyTabBtn")?.addEventListener("click", () => {
            if (active()) void listDrafts().catch(error => notice(error.message, true));
        });
    }

    window.addEventListener("nika:sale-completed", () => {
        if (!active()) return;
        saleSequence++;
        const consumedId = currentManualId;
        const consumedLegacyId = oldAutoId;
        currentManualId = null;
        oldAutoId = null;
        if (!consumedId && !consumedLegacyId) return;
        void queueWrite(async () => {
            if (consumedId) {
                await jsonRequest(api + "/" + consumedId, {method:"DELETE"});
            }
            if (consumedLegacyId) {
                await jsonRequest(api + "/" + consumedLegacyId, {method:"DELETE"});
            }
            await listDrafts();
        }).catch(() => { /* The completed sale must never be retried as a new sale. */ });
    });
    window.addEventListener("load", start);
})();