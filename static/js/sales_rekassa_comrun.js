(() => {
    "use strict";

    const OFD_PAYMENT_REQUIRED_CODE = "REKASSA_OFD_PAYMENT_REQUIRED";
    const state = { saleId: null, paymentUrl: "", checking: false };

    function ensureModal() {
        let modal = document.getElementById("comrunOfdModal");
        if (modal) return modal;

        const style = document.createElement("style");
        style.textContent = `
            .comrun-ofd-modal[hidden]{display:none!important}
            .comrun-ofd-modal{position:fixed;inset:0;z-index:10080;display:flex;align-items:center;justify-content:center;padding:18px;background:rgba(23,25,39,.48);backdrop-filter:blur(5px)}
            .comrun-ofd-dialog{width:min(520px,100%);overflow:hidden;border:1px solid #e8e8ef;border-radius:24px;background:#fff;box-shadow:0 28px 80px rgba(25,27,45,.22);color:#242738}
            .comrun-ofd-head{display:flex;gap:14px;align-items:flex-start;padding:22px 22px 15px}
            .comrun-ofd-icon{flex:0 0 46px;width:46px;height:46px;display:grid;place-items:center;border-radius:15px;background:#fff4dc;font-size:24px}
            .comrun-ofd-title{margin:0;font-size:19px;line-height:1.25;font-weight:850;letter-spacing:-.02em}
            .comrun-ofd-subtitle{margin:5px 0 0;color:#777e8f;font-size:12px;line-height:1.55}
            .comrun-ofd-body{padding:0 22px 20px}
            .comrun-ofd-note{padding:13px 14px;border:1px solid #e9e9f1;border-radius:15px;background:#fafafe;color:#555d70;font-size:12px;line-height:1.55}
            .comrun-ofd-note strong{color:#292d3d}
            .comrun-ofd-status{min-height:20px;margin-top:12px;color:#6c7385;font-size:12px;line-height:1.45}
            .comrun-ofd-status.is-success{color:#1b8f56}
            .comrun-ofd-status.is-error{color:#bd3d3d}
            .comrun-ofd-actions{display:grid;grid-template-columns:1fr 1fr;gap:9px;padding:0 22px 22px}
            .comrun-ofd-btn{min-height:44px;border:0;border-radius:13px;padding:0 14px;font:inherit;font-size:12px;font-weight:800;cursor:pointer;transition:.16s ease}
            .comrun-ofd-btn:disabled{cursor:wait;opacity:.65}
            .comrun-ofd-btn-primary{grid-column:1/-1;background:#7257ff;color:#fff}
            .comrun-ofd-btn-check{background:#edf8f2;color:#177d4b}
            .comrun-ofd-btn-close{background:#f2f3f7;color:#545b6c}
            @media(max-width:520px){.comrun-ofd-modal{align-items:flex-end;padding:10px}.comrun-ofd-dialog{border-radius:22px}.comrun-ofd-actions{grid-template-columns:1fr}.comrun-ofd-btn-primary{grid-column:auto}}
        `;
        document.head.appendChild(style);

        modal = document.createElement("div");
        modal.id = "comrunOfdModal";
        modal.className = "comrun-ofd-modal";
        modal.hidden = true;
        modal.setAttribute("aria-hidden", "true");
        modal.innerHTML = `
            <div class="comrun-ofd-dialog" role="dialog" aria-modal="true" aria-labelledby="comrunOfdTitle">
                <div class="comrun-ofd-head">
                    <div class="comrun-ofd-icon" aria-hidden="true">🧾</div>
                    <div><h2 class="comrun-ofd-title" id="comrunOfdTitle">Нужно оплатить ОФД COMRUN</h2><p class="comrun-ofd-subtitle">Продажа уже сохранена в Nika. Повторно проводить оплату не нужно.</p></div>
                </div>
                <div class="comrun-ofd-body">
                    <div class="comrun-ofd-note">reKassa не может фискализировать чек, пока не оплачено обслуживание ОФД COMRUN. После оплаты нажмите <strong>«Проверить оплату»</strong> — Nika повторно отправит <strong>эту же продажу</strong> в reKassa.</div>
                    <div class="comrun-ofd-status" id="comrunOfdStatus"></div>
                </div>
                <div class="comrun-ofd-actions">
                    <button type="button" class="comrun-ofd-btn comrun-ofd-btn-primary" id="comrunOfdPayBtn">Перейти к оплате COMRUN</button>
                    <button type="button" class="comrun-ofd-btn comrun-ofd-btn-check" id="comrunOfdCheckBtn">Проверить оплату</button>
                    <button type="button" class="comrun-ofd-btn comrun-ofd-btn-close" id="comrunOfdCloseBtn">Закрыть</button>
                </div>
            </div>`;
        document.body.appendChild(modal);

        modal.addEventListener("click", event => { if (event.target === modal) closeComrunOfdModal(); });
        document.getElementById("comrunOfdCloseBtn").addEventListener("click", closeComrunOfdModal);
        document.getElementById("comrunOfdPayBtn").addEventListener("click", () => {
            if (state.paymentUrl) window.open(state.paymentUrl, "_blank", "noopener,noreferrer");
        });
        document.getElementById("comrunOfdCheckBtn").addEventListener("click", checkComrunOfdPayment);
        return modal;
    }

    function setModalStatus(message, kind = "") {
        const status = document.getElementById("comrunOfdStatus");
        if (!status) return;
        status.className = "comrun-ofd-status" + (kind ? ` is-${kind}` : "");
        status.textContent = message || "";
    }

    function showComrunOfdModal(saleId, paymentUrl) {
        state.saleId = Number(saleId);
        state.paymentUrl = String(paymentUrl || "");
        const modal = ensureModal();
        document.getElementById("comrunOfdPayBtn").disabled = !state.paymentUrl;
        setModalStatus("");
        modal.hidden = false;
        modal.setAttribute("aria-hidden", "false");
    }

    function closeComrunOfdModal() {
        const modal = document.getElementById("comrunOfdModal");
        if (!modal) return;
        modal.hidden = true;
        modal.setAttribute("aria-hidden", "true");
        state.checking = false;
    }

    async function checkComrunOfdPayment() {
        if (!state.saleId || state.checking) return;
        const button = document.getElementById("comrunOfdCheckBtn");
        state.checking = true;
        button.disabled = true;
        button.textContent = "Проверяем…";
        setModalStatus("Проверяем COMRUN и повторно фискализируем сохранённую продажу…");

        try {
            const response = await fetch(`/api/rekassa/sales/${encodeURIComponent(state.saleId)}/fiscalize`, { method: "POST", headers: {"Content-Type": "application/json"} });
            const result = await response.json().catch(() => ({}));

            if (response.ok && result.fiscalized === true) {
                const saleId = state.saleId;
                setModalStatus("Оплата подтверждена. Чек успешно фискализирован.", "success");
                closeComrunOfdModal();
                window.dispatchEvent(new CustomEvent("nika:sale-completed"));
                if (typeof openSaleModal === "function") openSaleModal(saleId, {autoPrint: true});
                return;
            }

            if (result.code === OFD_PAYMENT_REQUIRED_CODE) {
                if (result.comrun_payment_url) {
                    state.paymentUrl = result.comrun_payment_url;
                    document.getElementById("comrunOfdPayBtn").disabled = false;
                }
                setModalStatus("Оплата ОФД пока не подтверждена. После оплаты в COMRUN нажмите «Проверить оплату» ещё раз.", "error");
                return;
            }

            if (result.code === "REKASSA_NOT_CONFIGURED" || result.configured === false) {
                const saleId = state.saleId;
                closeComrunOfdModal();
                if (typeof openSaleModal === "function") openSaleModal(saleId, {autoPrint: true});
                return;
            }

            setModalStatus(result.error || result.message || "Не удалось фискализировать чек. Продажа остаётся сохранённой в Nika.", "error");
        } catch (error) {
            console.error("COMRUN PAYMENT CHECK ERROR:", error);
            setModalStatus("Не удалось проверить оплату. Продажа сохранена — попробуйте проверить ещё раз позже.", "error");
        } finally {
            state.checking = false;
            button.disabled = false;
            button.textContent = "Проверить оплату";
        }
    }

    async function payWithComrunFlow() {
        if (typeof selectedClient === "undefined" || !selectedClient) { alert("Сначала выбери клиента"); return; }
        const currentCart = typeof cart !== "undefined" ? cart : [];
        if (!Array.isArray(currentCart) || !currentCart.length) { alert("Корзина пуста"); return; }

        const cash = document.getElementById("cashInput")?.value || 0;
        const card = document.getElementById("cardInput")?.value || 0;
        const kaspi = document.getElementById("kaspiInput")?.value || 0;
        let paymentMethod = "cash";
        if (parseFloat(card) > 0) paymentMethod = "card";
        if (parseFloat(kaspi) > 0) paymentMethod = "kaspi";

        try {
            const response = await fetch("/sales/pay", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({ client_id: selectedClient, cart: currentCart, payment_method: paymentMethod, cash, card, kaspi, kaspi_transaction_id: window.lastKaspiTransactionId || "", kaspi_method: window.lastKaspiMethod || "", company_id: null })
            });
            const data = await response.json().catch(() => null);
            if (!data || data.success !== true) { alert((data && (data.error || data.message)) || "Не удалось сохранить продажу"); return; }

            if (typeof cart !== "undefined") cart = [];
            if (typeof renderCart === "function") renderCart();
            if (typeof resetSaleAmounts === "function") resetSaleAmounts();
            window.dispatchEvent(new CustomEvent("nika:sale-completed"));

            const rekassa = data.rekassa || {};
            if (data.fiscalization_skipped === true || rekassa.configured === false || rekassa.status === "SKIPPED") {
                if (typeof openSaleModal === "function") openSaleModal(data.sale_id, {autoPrint: true});
                return;
            }
            if (data.fiscalized === true) {
                if (typeof openSaleModal === "function") openSaleModal(data.sale_id, {autoPrint: true});
                return;
            }
            if (rekassa.code === OFD_PAYMENT_REQUIRED_CODE) { showComrunOfdModal(data.sale_id, rekassa.comrun_payment_url); return; }

            alert("Продажа сохранена, но чек не фискализирован.\n\n" + (rekassa.message || "reKassa отклонила чек"));
            if (typeof openSaleModal === "function") openSaleModal(data.sale_id);
        } catch (error) {
            console.error("PAY ERROR:", error);
            alert("Не удалось сохранить продажу. Проверьте соединение и повторите попытку.");
        }
    }

    window.__nikaOriginalPay = window.pay;
    window.pay = payWithComrunFlow;
    window.showComrunOfdModal = showComrunOfdModal;
    window.closeComrunOfdModal = closeComrunOfdModal;
})();
