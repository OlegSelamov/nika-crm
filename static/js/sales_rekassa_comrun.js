(() => {
    "use strict";

    const OFD_PAYMENT_REQUIRED_CODE = "FISCAL_OFD_PAYMENT_REQUIRED";
    const state = {
        saleId: null,
        actionUrl: "",
        checking: false,
        configured: null,
        provider: null,
        providerName: null,
        capabilities: {},
    };

    function $(id) { return document.getElementById(id); }

    function hideFiscalUi() {
        if ($("shiftStrip")) $("shiftStrip").style.display = "none";
        if ($("salesHistoryShiftsMode")) $("salesHistoryShiftsMode").hidden = true;
        if ($("salesShiftsModeView")) $("salesShiftsModeView").hidden = true;
        if ($("salesDocumentsHistoryMode")) $("salesDocumentsHistoryMode").hidden = false;
        if (typeof switchSalesHistoryMode === "function") switchSalesHistoryMode("documents");
    }

    function showFiscalUi() {
        if ($("shiftStrip")) $("shiftStrip").style.display = "";
        if ($("salesHistoryShiftsMode")) $("salesHistoryShiftsMode").hidden = !state.capabilities.shifts;
    }

    function replaceProviderLabels(root = document) {
        if (!state.configured || !state.providerName || state.providerName === "reKassa") return;
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
        const nodes = [];
        while (walker.nextNode()) nodes.push(walker.currentNode);
        nodes.forEach(node => {
            if (node.nodeValue && node.nodeValue.includes("reKassa")) {
                node.nodeValue = node.nodeValue.replaceAll("reKassa", state.providerName);
            }
        });
    }

    async function loadFiscalContext() {
        try {
            const response = await fetch("/api/fiscal/status", { credentials: "same-origin" });
            const data = await response.json().catch(() => ({}));
            if (!response.ok || data.success === false) throw new Error(data.error || data.message || "Ошибка определения кассы");

            state.configured = Boolean(data.configured);
            state.provider = data.provider || null;
            state.providerName = data.provider_name || null;
            state.capabilities = data.capabilities || {};
            window.nikaFiscal = {
                configured: state.configured,
                provider: state.provider,
                providerName: state.providerName,
                capabilities: state.capabilities,
            };

            if (!state.configured) {
                hideFiscalUi();
                return;
            }
            showFiscalUi();
            replaceProviderLabels();
        } catch (error) {
            console.warn("FISCAL CONTEXT ERROR:", error);
            state.configured = false;
            hideFiscalUi();
        }
    }

    function ensureComrunModal() {
        let modal = $("comrunOfdModal");
        if (modal) return modal;

        const style = document.createElement("style");
        style.textContent = `
            .comrun-ofd-modal[hidden]{display:none!important}.comrun-ofd-modal{position:fixed;inset:0;z-index:10080;display:flex;align-items:center;justify-content:center;padding:18px;background:rgba(23,25,39,.48);backdrop-filter:blur(5px)}
            .comrun-ofd-dialog{width:min(520px,100%);overflow:hidden;border:1px solid #e8e8ef;border-radius:24px;background:#fff;box-shadow:0 28px 80px rgba(25,27,45,.22);color:#242738}.comrun-ofd-head{display:flex;gap:14px;align-items:flex-start;padding:22px 22px 15px}
            .comrun-ofd-icon{flex:0 0 46px;width:46px;height:46px;display:grid;place-items:center;border-radius:15px;background:#fff4dc;font-size:24px}.comrun-ofd-title{margin:0;font-size:19px;line-height:1.25;font-weight:850}.comrun-ofd-subtitle{margin:5px 0 0;color:#777e8f;font-size:12px;line-height:1.55}
            .comrun-ofd-body{padding:0 22px 20px}.comrun-ofd-note{padding:13px 14px;border:1px solid #e9e9f1;border-radius:15px;background:#fafafe;color:#555d70;font-size:12px;line-height:1.55}.comrun-ofd-status{min-height:20px;margin-top:12px;color:#6c7385;font-size:12px}.comrun-ofd-status.is-success{color:#1b8f56}.comrun-ofd-status.is-error{color:#bd3d3d}
            .comrun-ofd-actions{display:grid;grid-template-columns:1fr 1fr;gap:9px;padding:0 22px 22px}.comrun-ofd-btn{min-height:44px;border:0;border-radius:13px;padding:0 14px;font:inherit;font-size:12px;font-weight:800;cursor:pointer}.comrun-ofd-btn-primary{grid-column:1/-1;background:#7257ff;color:#fff}.comrun-ofd-btn-check{background:#edf8f2;color:#177d4b}.comrun-ofd-btn-close{background:#f2f3f7;color:#545b6c}
            @media(max-width:520px){.comrun-ofd-modal{align-items:flex-end;padding:10px}.comrun-ofd-actions{grid-template-columns:1fr}.comrun-ofd-btn-primary{grid-column:auto}}
        `;
        document.head.appendChild(style);

        modal = document.createElement("div");
        modal.id = "comrunOfdModal";
        modal.className = "comrun-ofd-modal";
        modal.hidden = true;
        modal.innerHTML = `
            <div class="comrun-ofd-dialog" role="dialog" aria-modal="true">
                <div class="comrun-ofd-head"><div class="comrun-ofd-icon">🧾</div><div><h2 class="comrun-ofd-title">Нужно оплатить ОФД COMRUN</h2><p class="comrun-ofd-subtitle">Продажа уже сохранена в Nika. Повторно проводить оплату не нужно.</p></div></div>
                <div class="comrun-ofd-body"><div class="comrun-ofd-note">Подключённая касса не может фискализировать чек, пока не оплачено обслуживание ОФД COMRUN. После оплаты нажмите <strong>«Проверить оплату»</strong> — Nika повторно отправит эту же продажу.</div><div class="comrun-ofd-status" id="comrunOfdStatus"></div></div>
                <div class="comrun-ofd-actions"><button class="comrun-ofd-btn comrun-ofd-btn-primary" id="comrunOfdPayBtn">Перейти к оплате COMRUN</button><button class="comrun-ofd-btn comrun-ofd-btn-check" id="comrunOfdCheckBtn">Проверить оплату</button><button class="comrun-ofd-btn comrun-ofd-btn-close" id="comrunOfdCloseBtn">Закрыть</button></div>
            </div>`;
        document.body.appendChild(modal);
        $("comrunOfdCloseBtn").onclick = closeComrunModal;
        $("comrunOfdPayBtn").onclick = () => { if (state.actionUrl) window.open(state.actionUrl, "_blank", "noopener,noreferrer"); };
        $("comrunOfdCheckBtn").onclick = retryFiscalization;
        return modal;
    }

    function setComrunStatus(message, kind = "") {
        const node = $("comrunOfdStatus");
        if (!node) return;
        node.className = "comrun-ofd-status" + (kind ? ` is-${kind}` : "");
        node.textContent = message || "";
    }

    function showComrunModal(saleId, actionUrl) {
        state.saleId = Number(saleId);
        state.actionUrl = String(actionUrl || "");
        const modal = ensureComrunModal();
        $("comrunOfdPayBtn").disabled = !state.actionUrl;
        setComrunStatus("");
        modal.hidden = false;
    }

    function closeComrunModal() {
        const modal = $("comrunOfdModal");
        if (modal) modal.hidden = true;
        state.checking = false;
    }

    async function retryFiscalization() {
        if (!state.saleId || state.checking) return;
        state.checking = true;
        const button = $("comrunOfdCheckBtn");
        button.disabled = true;
        button.textContent = "Проверяем…";
        setComrunStatus("Проверяем оплату и повторно фискализируем сохранённую продажу…");
        try {
            const response = await fetch(`/api/fiscal/sales/${encodeURIComponent(state.saleId)}/fiscalize`, { method: "POST", headers: {"Content-Type": "application/json"} });
            const result = await response.json().catch(() => ({}));
            if (response.ok && result.fiscalized === true) {
                const id = state.saleId;
                closeComrunModal();
                window.dispatchEvent(new CustomEvent("nika:sale-completed"));
                if (typeof openSaleModal === "function") openSaleModal(id, { autoPrint: true });
                return;
            }
            if (result.code === OFD_PAYMENT_REQUIRED_CODE) {
                state.actionUrl = result.action_url || result.comrun_payment_url || state.actionUrl;
                $("comrunOfdPayBtn").disabled = !state.actionUrl;
                setComrunStatus("Оплата ОФД пока не подтверждена. После оплаты нажмите «Проверить оплату» ещё раз.", "error");
                return;
            }
            if (result.configured === false || result.skipped === true) {
                const id = state.saleId;
                closeComrunModal();
                if (typeof openSaleModal === "function") openSaleModal(id, { autoPrint: true });
                return;
            }
            setComrunStatus(result.error || result.message || "Не удалось фискализировать чек. Продажа сохранена в Nika.", "error");
        } catch (error) {
            setComrunStatus("Не удалось проверить фискализацию. Продажа остаётся сохранённой.", "error");
        } finally {
            state.checking = false;
            button.disabled = false;
            button.textContent = "Проверить оплату";
        }
    }

    async function payWithFiscalLayer() {
        if (typeof selectedClient === "undefined" || !selectedClient) { alert("Сначала выбери клиента"); return; }
        const currentCart = typeof cart !== "undefined" ? cart : [];
        if (!Array.isArray(currentCart) || !currentCart.length) { alert("Корзина пуста"); return; }

        const cash = $("cashInput")?.value || 0;
        const card = $("cardInput")?.value || 0;
        const kaspi = $("kaspiInput")?.value || 0;
        let paymentMethod = "cash";
        if (parseFloat(card) > 0) paymentMethod = "card";
        if (parseFloat(kaspi) > 0) paymentMethod = "kaspi";

        try {
            const response = await fetch("/sales/pay", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({ client_id: selectedClient, cart: currentCart, payment_method: paymentMethod, cash, card, kaspi, kaspi_transaction_id: window.lastKaspiTransactionId || "", kaspi_method: window.lastKaspiMethod || "" })
            });
            const data = await response.json().catch(() => null);
            if (!data || data.success !== true) { alert((data && (data.error || data.message)) || "Не удалось сохранить продажу"); return; }

            if (typeof cart !== "undefined") cart = [];
            if (typeof renderCart === "function") renderCart();
            if (typeof resetSaleAmounts === "function") resetSaleAmounts();
            window.dispatchEvent(new CustomEvent("nika:sale-completed"));

            const fiscal = data.fiscal || data.rekassa || {};
            if (data.fiscalization_skipped === true || fiscal.configured === false || fiscal.status === "SKIPPED") {
                if (typeof openSaleModal === "function") openSaleModal(data.sale_id, { autoPrint: true });
                return;
            }
            if (data.fiscalized === true) {
                if (typeof openSaleModal === "function") openSaleModal(data.sale_id, { autoPrint: true });
                return;
            }
            if (fiscal.code === OFD_PAYMENT_REQUIRED_CODE) {
                showComrunModal(data.sale_id, fiscal.action_url || fiscal.comrun_payment_url);
                return;
            }

            const provider = fiscal.provider_name || state.providerName || "Подключённая касса";
            alert(`Продажа сохранена, но чек не фискализирован через ${provider}.\n\n${fiscal.message || "Касса отклонила чек"}`);
            if (typeof openSaleModal === "function") openSaleModal(data.sale_id);
        } catch (error) {
            console.error("PAY ERROR:", error);
            alert("Не удалось сохранить продажу. Проверьте соединение и повторите попытку.");
        }
    }

    const observer = new MutationObserver(mutations => {
        if (!state.configured || !state.providerName || state.providerName === "reKassa") return;
        mutations.forEach(m => m.addedNodes.forEach(node => {
            if (node.nodeType === Node.ELEMENT_NODE) replaceProviderLabels(node);
        }));
    });
    observer.observe(document.body, { childList: true, subtree: true });

    window.__nikaOriginalPay = window.pay;
    window.pay = payWithFiscalLayer;
    window.showComrunOfdModal = showComrunModal;
    window.closeComrunOfdModal = closeComrunModal;
    loadFiscalContext();
    window.addEventListener("nika:sale-completed", () => setTimeout(loadFiscalContext, 250));
})();
