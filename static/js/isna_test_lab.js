(function () {
    "use strict";

    const root = document.getElementById("isnaTestLab");
    if (!root) return;

    const checkButton = document.getElementById("isnaTestCheck");
    const signButton = document.getElementById("isnaTestSign");
    const downloadButton = document.getElementById("isnaTestDownload");
    const passwordLabel = document.getElementById("isnaTestPasswordLabel");
    const passwordInput = document.getElementById("isnaTestP12Password");
    const status = document.getElementById("isnaTestStatus");

    const mobile = Boolean(window.NikaMobileSigner &&
        typeof window.NikaMobileSigner.postMessage === "function");
    if (passwordLabel) passwordLabel.hidden = !mobile;

    let busy = false;
    let signedXml = "";
    let pendingMobile = null;

    function updateStatus(message) {
        status.textContent = String(message || "");
    }

    function setBusy(value) {
        busy = value;
        checkButton.disabled = value;
        signButton.disabled = value;
        downloadButton.disabled = value || !signedXml;
    }

    function demoXml() {
        // This is deliberately NOT a real ISNA FNO or SOAP service request.
        // No taxpayer, tenant or company data is sent to the signing bridge.
        const nonce = window.crypto && typeof crypto.randomUUID === "function"
            ? crypto.randomUUID() : String(Date.now());
        return '<?xml version="1.0" encoding="UTF-8"?>' +
            '<NikaIsnaTest xmlns="urn:nikabusiness:offline-signature-test:1">' +
            '<Purpose>Local XML signature compatibility check only</Purpose>' +
            '<Nonce>' + nonce + '</Nonce>' +
            '<Submission>false</Submission>' +
            '</NikaIsnaTest>';
    }

    async function readOnlyProbe() {
        setBusy(true);
        updateStatus("Проверяем TCP с TEST VPS. SOAP-запросы и отчёты не отправляются…");
        try {
            const response = await fetch("/accounting/isna/test/diagnostics", {
                method: "GET",
                credentials: "same-origin",
                cache: "no-store",
                headers: { "Accept": "application/json" }
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || "Недоступна диагностика.");
            updateStatus([
                "Среда: TEST",
                "Адрес: " + data.endpoint,
                "TCP с TEST VPS: " + (data.tcpOk ? "доступен" : "не подтверждён"),
                "Проверка: " + data.tcpMessage,
                "senderId: " + (data.senderConfigured ? "указан" : "не настроен"),
                "serviceId: " + (data.serviceIdConfigured ? "задан администратором (не проверен)" : "только значение по умолчанию (не проверено)"),
                "WS-Security signer: " + (data.transportSignerConfigured ? "задан (работоспособность не проверена)" : "не настроен"),
                data.note,
                "SOAP и налоговые документы не отправлялись."
            ].join("\n"));
        } catch (error) {
            updateStatus("Диагностика недоступна: " + (error?.message || "ошибка") +
                "\nНи один SOAP-запрос не отправлен.");
        } finally {
            setBusy(false);
        }
    }

    function mobileSignXml(xml) {
        const password = String(passwordInput?.value || "");
        if (!password) return Promise.reject(new Error("Введите пароль .p12 в тестовом приложении."));
        if (pendingMobile) return Promise.reject(new Error("Подписание уже выполняется."));
        return new Promise((resolve, reject) => {
            const requestId = "isna-test-" + Date.now() + "-" +
                Math.random().toString(16).slice(2);
            const timeoutId = window.setTimeout(() => {
                if (pendingMobile?.requestId !== requestId) return;
                pendingMobile = null;
                reject(new Error("Время ожидания мобильной подписи истекло."));
            }, 120000);
            pendingMobile = { requestId, resolve, reject, timeoutId };
            try {
                window.NikaMobileSigner.postMessage(JSON.stringify({
                    action: "signIsnaTestXml",
                    requestId,
                    payload: xml,
                    password
                }));
            } catch (error) {
                window.clearTimeout(timeoutId);
                pendingMobile = null;
                reject(error);
            }
        });
    }

    // Only used on this isolated TEST accounting page. Other Nika signing
    // modules still own their callbacks on their respective pages.
    if (mobile) {
        window.NikaMobileSignerResult = function (requestId, result) {
            if (!pendingMobile || String(requestId) !== pendingMobile.requestId) return;
            const request = pendingMobile;
            pendingMobile = null;
            window.clearTimeout(request.timeoutId);
            if (result && result.success) request.resolve(result);
            else request.reject(new Error(result?.error || "Мобильная подпись не выполнена."));
        };
    }

    async function signDemo() {
        setBusy(true);
        signedXml = "";
        downloadButton.disabled = true;
        updateStatus("Выберите ЭЦП и подпишите локальный тестовый XML. Сервер Nika ничего не получает.");
        try {
            const xml = demoXml();
            const result = mobile ? await mobileSignXml(xml) :
                await window.NikaNCALayer.signXml(xml);
            const value = String(result?.signedXml || "");
            // Presence of ds:Signature is not proof of cryptographic validity.
            if (!/<(?:[a-zA-Z0-9_]+:)?Signature(?:\s|>)/.test(value)) {
                throw new Error("Криптомодуль не вернул XML с элементом Signature.");
            }
            signedXml = value;
            updateStatus("Пробный XML подписан на устройстве. ✅\n" +
                "Подпись пока не проверена криптографически и НЕ соответствует " +
                "подтверждённому формату WS-Security Smart Bridge.\n" +
                "SOAP-запрос и налоговая форма не отправлены. " +
                "Можно сохранить XML для локального анализа.");
        } catch (error) {
            updateStatus("Подписание не завершено: " +
                (error?.message || "ошибка криптомодуля") +
                "\nОтправки в ИСНА не было.");
        } finally {
            // Do not keep the password in the page.
            if (passwordInput) passwordInput.value = "";
            setBusy(false);
        }
    }

    function downloadXml() {
        if (!signedXml) return;
        const blob = new Blob([signedXml], { type: "application/xml;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = "nika-isna-local-xml-signature-test.xml";
        link.hidden = true;
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    }

    checkButton.addEventListener("click", readOnlyProbe);
    signButton.addEventListener("click", signDemo);
    downloadButton.addEventListener("click", downloadXml);
})();
