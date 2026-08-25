(function () {
    "use strict";

    let saleId = null;
    let documentState = null;
    let products = [];
    let busy = false;

    const statusLabels = {
        new: "Новый",
        draft: "Черновик",
        prepared: "Готов к подписи",
        signed: "Подписан",
        sending: "Отправляется",
        sent: "Отправлен",
        accepted: "Принят ИС ЭСФ",
        rejected: "Отклонён",
        failed: "Ошибка"
    };

    function element(id) {
        return document.getElementById(id);
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function apiError(data, fallback) {
        return data && (data.error || data.message) ? (data.error || data.message) : fallback;
    }

    function dotDateToInput(value) {
        const match = String(value || "").match(/^(\d{2})\.(\d{2})\.(\d{4})$/);
        return match ? `${match[3]}-${match[2]}-${match[1]}` : String(value || "").slice(0, 10);
    }

    function getPath(object, path) {
        return path.split(".").reduce((value, key) => value && value[key], object);
    }

    function setPath(object, path, value) {
        const keys = path.split(".");
        const last = keys.pop();
        const target = keys.reduce((current, key) => {
            if (!current[key] || typeof current[key] !== "object") current[key] = {};
            return current[key];
        }, object);
        target[last] = value;
    }

    function showMessage(message, tone) {
        const box = element("esfMessage");
        if (!box) return;
        box.textContent = message || "";
        box.className = `esf-message ${tone ? `is-${tone}` : ""}`;
        box.hidden = !message;
    }

    function showValidation(errors) {
        const box = element("esfValidation");
        const list = element("esfValidationList");
        if (!box || !list) return;
        const items = Array.isArray(errors) ? errors : [];
        list.innerHTML = items.map((error) => `<li>${escapeHtml(error)}</li>`).join("");
        box.hidden = items.length === 0;
    }

    function setBusy(value, label) {
        busy = value;
        ["esfSaveDraft", "esfSign"].forEach((id) => {
            const button = element(id);
            if (button) button.disabled = value;
        });
        if (label) element("esfFooterStatus").textContent = label;
    }

    function renderStatus(documentData) {
        const status = documentData?.status || "new";
        const badge = element("esfStatusBadge");
        badge.textContent = statusLabels[status] || status;
        badge.dataset.status = status;
        element("esfSign").disabled = busy || !documentData?.can_sign;
        element("esfSend").disabled = true;
        const download = element("esfDownloadXml");
        download.hidden = !documentData?.id;
        if (documentData?.id && saleId) download.href = `/api/sales/${saleId}/esf/xml`;
        if (status === "signed") {
            element("esfFooterStatus").textContent = "Подпись сохранена. Документ ещё не отправлен в ИС ЭСФ.";
        } else if (status === "prepared") {
            element("esfFooterStatus").textContent = "Черновик проверен и готов к подписи.";
        } else if (status === "draft") {
            element("esfFooterStatus").textContent = "Черновик сохранён, но не все обязательные поля заполнены.";
        } else {
            element("esfFooterStatus").textContent = "Заполните реквизиты и сохраните черновик.";
        }
    }

    function renderProducts() {
        const body = element("esfProductsBody");
        body.innerHTML = products.map((product, index) => `
            <tr data-esf-product="${index}">
                <td><input data-product-field="description" value="${escapeHtml(product.description)}" aria-label="Наименование"></td>
                <td><div class="esf-quantity"><input data-product-field="quantity" type="number" min="0.000001" step="0.001" value="${escapeHtml(product.quantity)}"><span>${escapeHtml(product.unit_label || "")}</span></div></td>
                <td><input data-product-field="price_with_tax" type="number" min="0" step="0.01" value="${escapeHtml(product.price_with_tax)}"></td>
                <td><input data-product-field="catalog_tru_id" value="${escapeHtml(product.catalog_tru_id)}" aria-label="Идентификатор ТРУ"></td>
                <td>
                    <select data-product-field="tru_origin_code" aria-label="Признак происхождения">
                        <option value="">Выберите</option>
                        ${[1, 2, 3, 4, 5, 6].map((code) => `<option value="${code}" ${String(product.tru_origin_code) === String(code) ? "selected" : ""}>Код ${code}</option>`).join("")}
                    </select>
                </td>
                <td><input data-product-field="unit_code" inputmode="numeric" maxlength="10" value="${escapeHtml(product.unit_code)}" placeholder="необязательно"></td>
            </tr>
        `).join("");
    }

    function fillForm(payload) {
        document.querySelectorAll("#esfForm [data-esf]").forEach((input) => {
            let value = getPath(payload, input.dataset.esf) ?? "";
            if (input.type === "date") value = dotDateToInput(value);
            input.value = value;
        });
        products = (payload.products || []).map((product) => ({ ...product }));
        renderProducts();
    }

    function collectPayload() {
        const payload = JSON.parse(JSON.stringify(documentState?.payload || {}));
        document.querySelectorAll("#esfForm [data-esf]").forEach((input) => {
            setPath(payload, input.dataset.esf, input.value.trim());
        });
        payload.products = products.map((product, index) => {
            const row = document.querySelector(`[data-esf-product="${index}"]`);
            const next = { ...product };
            row?.querySelectorAll("[data-product-field]").forEach((input) => {
                next[input.dataset.productField] = input.value.trim();
            });
            return next;
        });
        return payload;
    }

    async function requestJson(url, options) {
        const response = await fetch(url, options);
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.success === false) {
            const error = new Error(apiError(data, "Не удалось выполнить операцию"));
            error.data = data;
            throw error;
        }
        return data;
    }

    async function saveDraft(options = {}) {
        if (!saleId || busy) return null;
        setBusy(true, "Сохраняем черновик…");
        showMessage("", "");
        try {
            const data = await requestJson(`/api/sales/${saleId}/esf/draft`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ payload: collectPayload() })
            });
            documentState = data.document;
            showValidation(documentState.validation_errors);
            renderStatus(documentState);
            if (!options.quiet) showMessage(data.message, documentState.can_sign ? "success" : "warning");
            return data;
        } catch (error) {
            showValidation(error.data?.validation_errors || []);
            showMessage(error.message, "error");
            return null;
        } finally {
            setBusy(false);
            renderStatus(documentState);
        }
    }

    async function signDraft() {
        if (!saleId || busy) return;
        const saved = await saveDraft({ quiet: true });
        if (!saved) return;
        if (saved.document.validation_errors?.length) {
            showMessage("Заполните отмеченные обязательные поля, затем повторите подпись.", "warning");
            return;
        }
        if (!window.NikaNCALayer) {
            showMessage("Модуль NCALayer не загружен. Обновите страницу.", "error");
            return;
        }

        setBusy(true, "Ожидаем выбор ключа в NCALayer…");
        showMessage("Откроется NCALayer. Выберите ключ компании и подтвердите подпись.", "info");
        try {
            const signed = await window.NikaNCALayer.signCmsDetached(saved.invoice_xml);
            const data = await requestJson(`/api/sales/${saleId}/esf/signature`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    signature: signed.signature,
                    certificate: signed.certificate,
                    certificate_subject: signed.certificateSubject,
                    payload_hash: saved.document.payload_hash
                })
            });
            documentState = data.document;
            renderStatus(documentState);
            showValidation(documentState.validation_errors);
            showMessage(data.message, "success");
        } catch (error) {
            const message = window.NikaNCALayer.friendlyError
                ? window.NikaNCALayer.friendlyError(error)
                : error.message;
            showMessage(message, "error");
        } finally {
            setBusy(false);
            renderStatus(documentState);
        }
    }

    async function openEsfModal(nextSaleId) {
        saleId = Number(nextSaleId);
        if (!Number.isFinite(saleId)) return;
        const modal = element("esfModal");
        modal.hidden = false;
        modal.setAttribute("aria-hidden", "false");
        document.body.classList.add("esf-modal-open");
        setBusy(true, "Загружаем данные продажи…");
        showMessage("", "");
        showValidation([]);
        try {
            const data = await requestJson(`/api/sales/${saleId}/esf`);
            documentState = data.document;
            fillForm(documentState.payload);
            showValidation(documentState.validation_errors);
            renderStatus(documentState);
        } catch (error) {
            showMessage(error.message, "error");
        } finally {
            setBusy(false);
            renderStatus(documentState);
        }
    }

    function closeEsfModal() {
        if (busy) return;
        const modal = element("esfModal");
        modal.hidden = true;
        modal.setAttribute("aria-hidden", "true");
        document.body.classList.remove("esf-modal-open");
    }

    document.addEventListener("DOMContentLoaded", () => {
        element("esfSaveDraft")?.addEventListener("click", () => saveDraft());
        element("esfSign")?.addEventListener("click", signDraft);
        element("esfModal")?.addEventListener("click", (event) => {
            if (event.target === element("esfModal")) closeEsfModal();
        });
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape" && !element("esfModal")?.hidden) closeEsfModal();
        });
    });

    window.openEsfModal = openEsfModal;
    window.closeEsfModal = closeEsfModal;
})();
