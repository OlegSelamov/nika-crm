(function () {
    "use strict";

    const SOCKET_URL = "wss://127.0.0.1:13579/";
    const SIGNING_OID = "1.3.6.1.5.5.7.3.4";
    const REQUEST_TIMEOUT_MS = 180000;
    const HANDSHAKE_TIMEOUT_MS = 15000;
    let socket = null;
    let connectPromise = null;
    let handshakeComplete = false;
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
        if (socket && socket.readyState === WebSocket.OPEN && handshakeComplete) {
            return Promise.resolve(socket);
        }
        if (connectPromise) return connectPromise;

        handshakeComplete = false;
        connectPromise = new Promise((resolve, reject) => {
            let settled = false;
            let currentSocket;
            try {
                currentSocket = new WebSocket(SOCKET_URL);
                socket = currentSocket;
            } catch (error) {
                connectPromise = null;
                reject(connectionError(error));
                return;
            }

            const timeoutId = window.setTimeout(() => {
                finishError(connectionError(new Error("NCALayer не прислал приветствие с версией.")));
            }, HANDSHAKE_TIMEOUT_MS);

            function cleanup() {
                window.clearTimeout(timeoutId);
                currentSocket.removeEventListener("message", onHandshake);
                currentSocket.removeEventListener("error", onError);
            }

            function finishError(error) {
                if (settled) return;
                settled = true;
                cleanup();
                connectPromise = null;
                handshakeComplete = false;
                if (socket === currentSocket) socket = null;
                try { currentSocket.close(); } catch (_) { /* уже закрыт */ }
                reject(error);
            }

            function onError(event) {
                finishError(connectionError(event));
            }

            function onHandshake(event) {
                if (settled) return;
                let response;
                try {
                    response = JSON.parse(event.data);
                } catch (error) {
                    finishError(new Error("NCALayer вернул неверное приветствие."));
                    return;
                }
                const version = versionValue(response);
                if (!version) return;
                settled = true;
                cleanup();
                handshakeComplete = true;
                connectPromise = null;
                resolve(currentSocket);
            }

            currentSocket.addEventListener("message", onHandshake);
            currentSocket.addEventListener("error", onError);
            currentSocket.addEventListener("close", () => {
                if (!settled) finishError(connectionError());
                if (socket === currentSocket) socket = null;
                handshakeComplete = false;
                connectPromise = null;
            }, { once: true });
        });
        return connectPromise;
    }

    function connectionError(cause) {
        const error = new Error("Не удалось подключиться к NCALayer.");
        error.code = "CONNECTION_ERROR";
        error.cause = cause;
        return error;
    }

    function versionValue(response) {
        const candidates = [
            response?.result?.version,
            response?.body?.result?.version,
            response?.body?.version,
            response?.version
        ];
        for (const candidate of candidates) {
            if (candidate) return String(candidate);
        }

        const directResult = response?.body?.result ?? response?.result;
        if (typeof directResult !== "string" || directResult.length > 100) return "";
        return /ncalayer|^v?\d+(?:\.\d+){1,3}/i.test(directResult.trim())
            ? directResult.trim()
            : "";
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

                // Some NCALayer builds repeat the service/version message after
                // the first request. It is not the operation result, so keep
                // waiting instead of forcing the user to click Sign twice.
                if (versionValue(response)) return;

                if (response.status === false) {
                    cleanup();
                    const error = new Error(response.message || response.code || "NCALayer не выполнил операцию.");
                    error.code = response.code || "NCALAYER_ERROR";
                    error.details = response.details;
                    reject(error);
                    return;
                }

                if (response.status === true) {
                    cleanup();
                    resolve(response.body && Object.prototype.hasOwnProperty.call(response.body, "result")
                        ? response.body.result
                        : response.body);
                    return;
                }

                // Compatibility with builds that return a direct result without
                // the top-level status flag.
                if (response.body && Object.prototype.hasOwnProperty.call(response.body, "result")) {
                    cleanup();
                    resolve(response.body.result);
                    return;
                }
                if (Object.prototype.hasOwnProperty.call(response, "result")) {
                    cleanup();
                    resolve(response.result);
                    return;
                }
                if (response.code || response.message) {
                    cleanup();
                    const error = new Error(response.message || response.code);
                    error.code = response.code || "NCALAYER_ERROR";
                    error.details = response.details;
                    reject(error);
                }
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

    function certificateString(value) {
        if (typeof value === "string") return value.trim();
        if (Array.isArray(value)) {
            for (const item of value) {
                const found = certificateString(item);
                if (found) return found;
            }
            return "";
        }
        if (!value || typeof value !== "object") return "";
        for (const key of ["value", "pem", "base64", "data", "certificate", "cert", "x509Certificate"]) {
            const found = certificateString(value[key]);
            if (found) return found;
        }
        return "";
    }

    function certificateValue(result) {
        if (!result || typeof result !== "object") return "";
        if (Array.isArray(result)) {
            for (const item of result) {
                if (!item || typeof item !== "object") continue;
                const found = certificateValue(item);
                if (found) return found;
            }
            return "";
        }
        for (const key of ["certificate", "certificates", "cert", "certs", "x509Certificate", "x509Certificates"]) {
            const found = certificateString(result[key]);
            if (found) return found;
        }
        if (Array.isArray(result.signatures)) {
            for (const signature of result.signatures) {
                const found = certificateValue(signature);
                if (found) return found;
            }
        }
        if (result.signature && typeof result.signature === "object") {
            return certificateValue(result.signature);
        }
        return "";
    }

    function certificateSubjectValue(result) {
        if (!result || typeof result !== "object") return "";
        if (Array.isArray(result)) {
            for (const item of result) {
                const found = certificateSubjectValue(item);
                if (found) return found;
            }
            return "";
        }
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

    async function signRaw(data) {
        const result = await sendRequest({
            module: "kz.gov.pki.knca.basics",
            method: "sign",
            args: {
                // IS ESF expects the raw signature (max 400 characters) and
                // the X.509 certificate in a separate request field.
                format: "raw",
                data,
                signingParams: {
                    decode: false,
                    outputCert: true
                },
                signerParams: {
                    extKeyUsageOids: [SIGNING_OID],
                    chain: null
                },
                locale: "ru"
            }
        });
        const certificate = certificateValue(result);
        if (!certificate) {
            const responseShape = result && typeof result === "object"
                ? Object.keys(result).join(", ")
                : typeof result;
            console.warn("NCALayer raw-sign response has no recognized certificate field. Keys:", responseShape);
            throw new Error(`NCALayer подписал документ, но не вернул сертификат. Поля ответа: ${responseShape || "пусто"}.`);
        }
        const signature = signedValue(result);
        if (!signature || signature.length > 400) {
            throw new Error("NCALayer вернул подпись не в формате ИС ЭСФ. Обновите страницу и подпишите документ заново.");
        }
        return {
            signature,
            certificate,
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
        signRaw,
        // Kept temporarily for pages from an older browser cache.
        signCmsDetached: signRaw
    });

    document.addEventListener("DOMContentLoaded", () => {
        document.getElementById("ncalayerCheck")?.addEventListener("click", checkNcalayer);
        document.getElementById("ncalayerSignTest")?.addEventListener("click", signTestXml);
        document.getElementById("ncalayerDownloadSignature")?.addEventListener("click", downloadSignedXml);
    });
})();
