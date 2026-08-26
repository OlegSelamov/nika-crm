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
        failed: "Ошибка",
        revoking: "Отзывается",
        revoke_pending: "Ожидает подтверждения",
        revoked: "Отозван",
        revoke_failed: "Ошибка отзыва"
    };

    const authStorageKey = "nikaEsfAuthPreferences";

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
        const message = data && (data.error || data.message) ? (data.error || data.message) : fallback;
        const details = Array.isArray(data?.details) ? data.details.filter(Boolean) : [];
        return details.length ? `${message} ${details.join("; ")}` : message;
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
        ["esfSaveDraft", "esfSign", "esfCheckAuth", "esfSend", "esfRevoke"].forEach((id) => {
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
        const locked = Boolean(documentData?.external_id);
        element("esfSaveDraft").disabled = busy || locked;
        element("esfSign").disabled = busy || !documentData?.can_sign;
        element("esfSend").disabled = busy || !documentData?.can_send;
        const revoke = element("esfRevoke");
        revoke.hidden = !documentData?.can_revoke;
        revoke.disabled = busy || !documentData?.can_revoke;
        const authPanel = element("esfApiPanel");
        const authAvailable = Boolean(documentData?.can_send || documentData?.can_revoke);
        if (authPanel) authPanel.hidden = !authAvailable;
        const checkAuth = element("esfCheckAuth");
        if (checkAuth) checkAuth.disabled = busy || !authAvailable;
        const revokePanel = element("esfRevokePanel");
        if (revokePanel) revokePanel.hidden = !documentData?.can_revoke;
        document.querySelectorAll("#esfForm input, #esfForm select").forEach((input) => {
            input.disabled = locked;
        });
        const environment = documentData?.api_environment || "test";
        const environmentBadge = element("esfApiEnvironment");
        if (environmentBadge) {
            environmentBadge.textContent = environment === "production" ? "БОЕВАЯ ИС ЭСФ" : "ТЕСТОВАЯ ИС ЭСФ";
            environmentBadge.classList.toggle("is-production", environment === "production");
        }
        const remoteMeta = element("esfRemoteMeta");
        if (remoteMeta) {
            const meta = [];
            if (documentData?.external_id) meta.push(`ID ИС ЭСФ: ${documentData.external_id}`);
            if (documentData?.registration_number) meta.push(`Регистрационный номер: ${documentData.registration_number}`);
            remoteMeta.textContent = meta.join(" · ");
            remoteMeta.hidden = meta.length === 0;
        }
        const download = element("esfDownloadXml");
        download.hidden = !documentData?.id;
        if (documentData?.id && saleId) download.href = `/api/sales/${saleId}/esf/xml`;
        if (status === "signed") {
            element("esfFooterStatus").textContent = "Подпись сохранена. Можно отправлять документ в ИС ЭСФ.";
        } else if (status === "sending") {
            element("esfFooterStatus").textContent = "Документ отправляется в ИС ЭСФ…";
        } else if (status === "sent" || status === "accepted") {
            element("esfFooterStatus").textContent = "Документ отправлен. Его ID сохранён в Nika.";
        } else if (status === "revoking") {
            element("esfFooterStatus").textContent = "Заявка на отзыв отправляется…";
        } else if (status === "revoke_pending") {
            element("esfFooterStatus").textContent = "Отзыв ожидает подтверждения получателя в ИС ЭСФ.";
        } else if (status === "revoked") {
            element("esfFooterStatus").textContent = "Документ отозван в ИС ЭСФ.";
        } else if (status === "failed" || status === "revoke_failed") {
            element("esfFooterStatus").textContent = documentData?.error_message || "ИС ЭСФ вернула ошибку. Исправьте данные и повторите.";
        } else if (status === "prepared") {
            element("esfFooterStatus").textContent = "Черновик проверен и готов к подписи.";
        } else if (status === "draft") {
            element("esfFooterStatus").textContent = "Черновик сохранён, но не все обязательные поля заполнены.";
        } else {
            element("esfFooterStatus").textContent = "Заполните реквизиты и сохраните черновик.";
        }
    }

    function loadAuthPreferences() {
        try {
            const saved = JSON.parse(localStorage.getItem(authStorageKey) || "{}");
            if (saved.iin) element("esfAuthIin").value = saved.iin;
            if (saved.profileType) element("esfAuthProfile").value = saved.profileType;
        } catch (_) {
            localStorage.removeItem(authStorageKey);
        }
    }

    function authCredentials() {
        const iin = String(element("esfAuthIin")?.value || "").replace(/\D/g, "");
        const password = String(element("esfAuthPassword")?.value || "");
        const profileType = String(element("esfAuthProfile")?.value || "ADMIN_ENTERPRISE");
        if (!/^\d{12}$/.test(iin)) throw new Error("Укажите ИИН пользователя ИС ЭСФ — ровно 12 цифр.");
        if (!password) throw new Error("Введите пароль пользователя ИС ЭСФ.");
        localStorage.setItem(authStorageKey, JSON.stringify({ iin, profileType }));
        return { iin, password, profile_type: profileType };
    }

    async function authorize() {
        if (!window.NikaNCALayer) throw new Error("Модуль NCALayer не загружен. Обновите страницу.");
        const credentials = authCredentials();
        element("esfFooterStatus").textContent = "Получаем одноразовый тикет ИС ЭСФ…";
        const ticket = await requestJson(`/api/sales/${saleId}/esf/auth-ticket`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ iin: credentials.iin })
        });
        if (documentState && ticket.api_environment) {
            documentState.api_environment = ticket.api_environment;
            renderStatus(documentState);
        }
        element("esfFooterStatus").textContent = "Подпишите тикет авторизации в NCALayer…";
        const signedTicket = await window.NikaNCALayer.signXml(ticket.auth_ticket_xml);
        if (!signedTicket.signedXml || !String(signedTicket.signedXml).includes("Signature")) {
            throw new Error("NCALayer не вернул подписанный тикет авторизации.");
        }
        return { ...credentials, signed_auth_ticket: signedTicket.signedXml };
    }

    function confirmApiAction(action) {
        const production = documentState?.api_environment === "production";
        const prefix = production ? "ВНИМАНИЕ: это БОЕВАЯ ИС ЭСФ." : "Это тестовая ИС ЭСФ.";
        const seller = documentState?.payload?.seller || {};
        const customer = documentState?.payload?.customer || {};
        const parties = production
            ? `\n\nПоставщик: ${seller.name || "—"} (${seller.tin || "—"})` +
              `\nПолучатель: ${customer.name || "—"} (${customer.tin || "—"})`
            : "";
        return window.confirm(`${prefix}${parties}\n\n${action}`);
    }

    function friendlyOperationError(error) {
        if (error?.data) return apiError(error.data, error.message);
        return window.NikaNCALayer?.friendlyError
            ? window.NikaNCALayer.friendlyError(error)
            : (error?.message || "Не удалось выполнить операцию.");
    }

    async function checkEsfAuth() {
        if (!saleId || busy || !(documentState?.can_send || documentState?.can_revoke)) return;
        setBusy(true, "Проверяем авторизацию в ИС ЭСФ…");
        showMessage("Проверяем только вход в ИС ЭСФ. Документ отправлен не будет.", "info");
        try {
            const auth = await authorize();
            element("esfFooterStatus").textContent = "Открываем проверочную API-сессию…";
            const data = await requestJson(`/api/sales/${saleId}/esf/auth-check`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(auth)
            });
            if (documentState && data.api_environment) {
                documentState.api_environment = data.api_environment;
            }
            showMessage(data.message, "success");
            element("esfFooterStatus").textContent = "Авторизация проверена. Документ не отправлялся.";
        } catch (error) {
            showMessage(friendlyOperationError(error), "error");
        } finally {
            if (element("esfAuthPassword")) element("esfAuthPassword").value = "";
            setBusy(false);
            renderStatus(documentState);
        }
    }

    async function sendEsf() {
        if (!saleId || busy || !documentState?.can_send) return;
        if (!confirmApiAction("Отправить подписанную ЭСФ?")) return;
        setBusy(true, "Готовим авторизацию в ИС ЭСФ…");
        showMessage("Для входа в ИС ЭСФ NCALayer попросит выбрать ключ компании.", "info");
        try {
            const auth = await authorize();
            element("esfFooterStatus").textContent = "Отправляем подписанный документ в ИС ЭСФ…";
            const data = await requestJson(`/api/sales/${saleId}/esf/send`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(auth)
            });
            documentState = data.document;
            showMessage(`${data.message} Перед отзывом дождитесь появления ЭСФ в обычном кабинете ИС ЭСФ.`, "success");
        } catch (error) {
            showMessage(friendlyOperationError(error), "error");
        } finally {
            if (element("esfAuthPassword")) element("esfAuthPassword").value = "";
            setBusy(false);
            renderStatus(documentState);
        }
    }

    async function revokeEsf() {
        if (!saleId || busy || !documentState?.can_revoke) return;
        const reason = String(element("esfRevokeReason")?.value || "").trim();
        if (reason.length < 3) {
            showMessage("Укажите причину отзыва — минимум 3 символа.", "warning");
            return;
        }
        if (!confirmApiAction("Отправить запрос на отзыв этой ЭСФ?")) return;
        setBusy(true, "Готовим отзыв ЭСФ…");
        showMessage("Потребуются подписи тикета авторизации и заявления на отзыв.", "info");
        try {
            const auth = await authorize();
            const prepared = await requestJson(`/api/sales/${saleId}/esf/revoke/prepare`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ reason })
            });
            element("esfFooterStatus").textContent = "Подпишите заявление на отзыв в NCALayer…";
            const signed = await window.NikaNCALayer.signRaw(prepared.signable_xml);
            if (!signed.signature || !signed.certificate) {
                throw new Error("NCALayer не вернул подпись и сертификат для отзыва.");
            }
            element("esfFooterStatus").textContent = "Отправляем заявление на отзыв в ИС ЭСФ…";
            const data = await requestJson(`/api/sales/${saleId}/esf/revoke`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    ...auth,
                    reason,
                    revoke_signature: signed.signature,
                    revoke_certificate: signed.certificate
                })
            });
            documentState = data.document;
            showMessage(data.message, "success");
        } catch (error) {
            showMessage(friendlyOperationError(error), "error");
        } finally {
            if (element("esfAuthPassword")) element("esfAuthPassword").value = "";
            setBusy(false);
            renderStatus(documentState);
        }
    }

    function renderProducts() {
        const body = element("esfProductsBody");
        body.innerHTML = products.map((product, index) => `
            <tr data-esf-product="${index}">
                <td><input data-product-field="description" value="${escapeHtml(product.description)}" aria-label="Наименование"></td>
                <td><div class="esf-quantity"><input data-product-field="quantity" type="number" min="0.000001" step="0.001" value="${escapeHtml(product.quantity)}"><span>${escapeHtml(product.unit_label || "")}</span></div></td>
                <td><input data-product-field="price_with_tax" type="number" min="0" step="0.01" value="${escapeHtml(product.price_with_tax)}"></td>
                <td><input data-product-field="catalog_tru_id" value="${escapeHtml(product.item_type === "service" ? "1" : product.catalog_tru_id)}" aria-label="Идентификатор ТРУ" ${product.item_type === "service" ? 'readonly title="Для работ и услуг Nika использует ID ТРУ 1"' : 'title="Для товара ВС укажите реальный составной код ГСВС; для товара вне ВС допустимо значение, предусмотренное ИС ЭСФ"'}></td>
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
            const signed = await window.NikaNCALayer.signRaw(saved.invoice_xml);
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
        loadAuthPreferences();
        element("esfSaveDraft")?.addEventListener("click", () => saveDraft());
        element("esfSign")?.addEventListener("click", signDraft);
        element("esfCheckAuth")?.addEventListener("click", checkEsfAuth);
        element("esfSend")?.addEventListener("click", sendEsf);
        element("esfRevoke")?.addEventListener("click", revokeEsf);
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
