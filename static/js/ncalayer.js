(function () {
    "use strict";

    const SOCKET_URL = "wss://127.0.0.1:13579/";
    const SIGNING_OID = "1.3.6.1.5.5.7.3.4";
    const REQUEST_TIMEOUT_MS = 180000;
    let socket = null;
    let lastSignedXml = "";

    function statusElement() {
        return document.getElementById("ncalayerStatus");
    }

    function setStatus(message, state) {
        const element = statusElement();
        if (!element) return;
        element.textContent = message;
        element.dataset.state = state || "neutral";
    }

    function setBusy(isBusy) {
        document.querySelectorAll("[data-ncalayer-action]").forEach((button) => {
            button.disabled = isBusy;
        });
    }

    function friendlyError(error) {
        const code = error && error.code ? String(error.code) : "";
        if (code === "USER_CANCELLED" || code === "CANCELED_BY_USER") {
            return "Подписание отменено пользователем.";
        }
        if (code === "REQUEST_TIMEOUT") {
            return "NCALayer не ответил вовремя. Повторите попытку.";
        }
        if (code === "CONNECTION_ERROR") {
            return "Не удалось подключиться. Запустите NCALayer на этом компьютере и повторите проверку.";
        }
        if (error && error.message) return error.message;
        return "Неизвестная ошибка NCALayer.";
    }

    function connect() {
        if (socket && socket.readyState === WebSocket.OPEN) {
            return Promise.resolve(socket);
        }
        if (socket && socket.readyState === WebSocket.CONNECTING) {
            return new Promise((resolve, reject) => {
                socket.addEventListener("open", () => resolve(socket), { once: true });
                socket.addEventListener("error", () => rejectConnection(reject), { once: true });
            });
        }

        return new Promise((resolve, reject) => {
            try {
                socket = new WebSocket(SOCKET_URL);
            } catch (error) {
                reject(connectionError(error));
                return;
            }

            socket.addEventListener("open", () => resolve(socket), { once: true });
            socket.addEventListener("error", () => rejectConnection(reject), { once: true });
            socket.addEventListener("close", () => {
                socket = null;
            }, { once: true });
        });
    }

    function connectionError(cause) {
        const error = new Error("Не удалось подключиться к NCALayer.");
        error.code = "CONNECTION_ERROR";
        error.cause = cause;
        return error;
    }

    function rejectConnection(reject) {
        socket = null;
        reject(connectionError());
    }

    async function sendRequest(payload) {
        const webSocket = await connect();

        return new Promise((resolve, reject) => {
            let settled = false;
            const timeoutId = window.setTimeout(() => {
                cleanup();
                const error = new Error("NCALayer не ответил вовремя.");
                error.code = "REQUEST_TIMEOUT";
                reject(error);
            }, REQUEST_TIMEOUT_MS);

            function cleanup() {
                if (settled) return;
                settled = true;
                window.clearTimeout(timeoutId);
                webSocket.removeEventListener("message", onMessage);
                webSocket.removeEventListener("close", onClose);
                webSocket.removeEventListener("error", onError);
            }

            function onClose() {
                if (settled) return;
                cleanup();
                reject(connectionError());
            }

            function onError() {
                if (settled) return;
                cleanup();
                reject(connectionError());
            }

            function onMessage(event) {
                if (settled) return;
                let response;
                try {
                    response = JSON.parse(event.data);
                } catch (error) {
                    cleanup();
                    reject(new Error("NCALayer вернул ответ в неизвестном формате."));
                    return;
                }

                cleanup();
                if (response.status !== true) {
                    const error = new Error(response.message || response.code || "NCALayer не выполнил операцию.");
                    error.code = response.code || "NCALAYER_ERROR";
                    error.details = response.details;
                    reject(error);
                    return;
                }

                resolve(response.body && Object.prototype.hasOwnProperty.call(response.body, "result")
                    ? response.body.result
                    : response.body);
            }

            webSocket.addEventListener("message", onMessage);
            webSocket.addEventListener("close", onClose);
            webSocket.addEventListener("error", onError);

            try {
                webSocket.send(JSON.stringify(payload));
            } catch (error) {
                cleanup();
                reject(connectionError(error));
            }
        });
    }

    function buildTestXml() {
        const timestamp = new Date().toISOString();
        return [
            '<?xml version="1.0" encoding="UTF-8"?>',
            "<nikaNcalayerTest>",
            "  <purpose>Проверка локальной подписи Nika Business</purpose>",
            `  <createdAt>${timestamp}</createdAt>`,
            "  <notice>Документ не отправляется в ИС ЭСФ или другие государственные системы.</notice>",
            "</nikaNcalayerTest>"
        ].join("\n");
    }

    function signedValue(result) {
        if (typeof result === "string") return result;
        if (Array.isArray(result)) {
            if (result.length === 1) return signedValue(result[0]);
            return result.map(signedValue).join("\n");
        }
        if (result && Array.isArray(result.signatures)) {
            if (result.signatures.length === 1) return signedValue(result.signatures[0]);
            return result.signatures.map(signedValue).join("\n");
        }
        if (result && typeof result.signatures === "string") return result.signatures;
        if (result && typeof result.signature === "string") return result.signature;
        if (result && typeof result.signedXml === "string") return result.signedXml;
        if (result && typeof result.signedData === "string") return result.signedData;
        return JSON.stringify(result, null, 2);
    }

    function certificateValue(result) {
        if (!result || typeof result !== "object") return "";
        if (typeof result.certificate === "string") return result.certificate;
        if (typeof result.cert === "string") return result.cert;
        if (typeof result.x509Certificate === "string") return result.x509Certificate;
        if (Array.isArray(result.certificates) && result.certificates.length) {
            return String(result.certificates[0] || "");
        }
        if (Array.isArray(result.signatures) && result.signatures.length) {
            return certificateValue(result.signatures[0]);
        }
        if (result.signature && typeof result.signature === "object") {
            return certificateValue(result.signature);
        }
        return "";
    }

    function certificateSubjectValue(result) {
        if (!result || typeof result !== "object") return "";
        const value = result.certificateSubject || result.subject || result.subjectDn;
        if (value) return String(value);
        if (Array.isArray(result.signatures) && result.signatures.length) {
            return certificateSubjectValue(result.signatures[0]);
        }
        return "";
    }

    async function signXml(xml) {
        const result = await sendRequest({
            module: "kz.gov.pki.knca.basics",
            method: "sign",
            args: {
                format: "xml",
                data: xml,
                signingParams: {},
                signerParams: {
                    extKeyUsageOids: [SIGNING_OID],
                    chain: null
                },
                locale: "ru"
            }
        });
        return {
            signedXml: signedValue(result),
            certificate: certificateValue(result),
            certificateSubject: certificateSubjectValue(result),
            raw: result
        };
    }

    async function signCmsDetached(data) {
        const result = await sendRequest({
            module: "kz.gov.pki.knca.basics",
            method: "sign",
            args: {
                format: "cms",
                data,
                signingParams: {
                    decode: false,
                    encapsulate: false,
                    digested: false,
                    tsaProfile: null,
                    outputCert: true
                },
                signerParams: {
                    extKeyUsageOids: [SIGNING_OID],
                    chain: null
                },
                locale: "ru"
            }
        });
        return {
            signature: signedValue(result),
            certificate: certificateValue(result),
            certificateSubject: certificateSubjectValue(result),
            raw: result
        };
    }

    async function checkNcalayer() {
        setBusy(true);
        setStatus("Подключаемся к NCALayer…", "loading");
        try {
            await connect();
            setStatus("NCALayer запущен и доступен этому браузеру.", "success");
        } catch (error) {
            setStatus(friendlyError(error), "error");
        } finally {
            setBusy(false);
        }
    }

    async function signTestXml() {
        setBusy(true);
        setStatus("Ожидаем выбор ключа и подпись в NCALayer…", "loading");
        const resultField = document.getElementById("ncalayerSignatureResult");
        const downloadButton = document.getElementById("ncalayerDownloadSignature");

        try {
            const result = await signXml(buildTestXml());

            lastSignedXml = result.signedXml;
            if (resultField) {
                resultField.value = lastSignedXml;
                resultField.hidden = false;
            }
            if (downloadButton) downloadButton.hidden = false;
            setStatus("Готово: NCALayer успешно подписал тестовый XML. В Nika и ИС ЭСФ ничего не отправлялось.", "success");
        } catch (error) {
            console.error("NCALayer signing error:", error);
            setStatus(friendlyError(error), "error");
        } finally {
            setBusy(false);
        }
    }

    function downloadSignedXml() {
        if (!lastSignedXml) return;
        const blob = new Blob([lastSignedXml], { type: "application/xml;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = "nika-ncalayer-test-signed.xml";
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        URL.revokeObjectURL(url);
    }

    window.NikaNCALayer = Object.freeze({
        connect,
        check: connect,
        friendlyError,
        signXml,
        signCmsDetached
    });

    document.addEventListener("DOMContentLoaded", () => {
        document.getElementById("ncalayerCheck")?.addEventListener("click", checkNcalayer);
        document.getElementById("ncalayerSignTest")?.addEventListener("click", signTestXml);
        document.getElementById("ncalayerDownloadSignature")?.addEventListener("click", downloadSignedXml);
    });
})();
