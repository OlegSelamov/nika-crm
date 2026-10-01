const { contextBridge, ipcRenderer } = require("electron");

function prepareReceiptPayload(payload = {}) {
    if (!payload || typeof payload !== "object") return payload;
    if (typeof payload.html !== "string" || !payload.html.trim()) return payload;

    const printReadabilityStyle = `
        <style data-nika-electron-receipt-readability>
            .receipt .item-extra {
                font-size: 12px !important;
                font-weight: 700 !important;
                line-height: 1.35 !important;
                color: #000 !important;
                margin-top: 2px !important;
                overflow-wrap: anywhere !important;
            }
        </style>`;

    let html = payload.html;
    if (!html.includes("data-nika-electron-receipt-readability")) {
        if (/<\/body>/i.test(html)) {
            html = html.replace(/<\/body>/i, `${printReadabilityStyle}</body>`);
        } else {
            html += printReadabilityStyle;
        }
    }

    return { ...payload, html };
}

function installElectronFocusGuard() {
    let lastEditable = null;
    let restoreTimer = null;

    const editableSelector = [
        "input:not([type='button']):not([type='submit']):not([type='reset']):not([type='checkbox']):not([type='radio'])",
        "textarea",
        "select",
        "[contenteditable='true']"
    ].join(",");

    function editableFromNode(node) {
        if (!node || node.nodeType !== 1) return null;
        const target = node.matches?.(editableSelector)
            ? node
            : node.closest?.(editableSelector);
        if (!target || target.disabled) return null;
        if (target.readOnly === true) return null;
        return target;
    }

    function rememberEditable(target) {
        if (target && target.isConnected) lastEditable = target;
    }

    function focusEditable(target, { force = false } = {}) {
        if (!target || !target.isConnected || target.disabled || target.readOnly === true) return;

        window.clearTimeout(restoreTimer);
        restoreTimer = window.setTimeout(() => {
            if (!target.isConnected || target.disabled || target.readOnly === true) return;

            try {
                // Chromium can occasionally leave the renderer without keyboard
                // focus while the BrowserWindow itself still looks active.
                window.focus();

                if (force || document.activeElement !== target || !document.hasFocus()) {
                    target.focus({ preventScroll: true });
                }
            } catch (error) {
                try { target.focus(); } catch (_) {}
            }
        }, 0);
    }

    document.addEventListener("focusin", (event) => {
        const target = editableFromNode(event.target);
        if (target) rememberEditable(target);
    }, true);

    // Main recovery path: when the user explicitly clicks/taps an editable
    // control, force keyboard focus back to that exact control. This is safe
    // for barcode scanners because ordinary key events are not redirected.
    document.addEventListener("pointerdown", (event) => {
        const target = editableFromNode(event.target);
        if (!target) return;
        rememberEditable(target);
        focusEditable(target, { force: true });
    }, true);

    // Fallback for older Chromium/Windows combinations where pointer events
    // can be inconsistent after restoring a window.
    document.addEventListener("mousedown", (event) => {
        const target = editableFromNode(event.target);
        if (!target) return;
        rememberEditable(target);
        focusEditable(target, { force: true });
    }, true);

    window.addEventListener("blur", () => {
        const target = editableFromNode(document.activeElement);
        if (target) rememberEditable(target);
    }, true);

    window.addEventListener("focus", () => {
        const active = editableFromNode(document.activeElement);
        if (active) {
            rememberEditable(active);
            focusEditable(active);
            return;
        }

        // Do not steal focus from buttons/modals. Restore the previous field
        // only when Chromium has fallen back to BODY/HTML after window focus.
        const current = document.activeElement;
        const lostInsidePage = !current || current === document.body || current === document.documentElement;
        if (lostInsidePage && lastEditable?.isConnected) {
            focusEditable(lastEditable);
        }
    }, true);

    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState !== "visible") return;
        const current = document.activeElement;
        const lostInsidePage = !current || current === document.body || current === document.documentElement;
        if (lostInsidePage && lastEditable?.isConnected) {
            focusEditable(lastEditable);
        }
    }, true);

    window.addEventListener("pageshow", () => {
        const current = document.activeElement;
        const lostInsidePage = !current || current === document.body || current === document.documentElement;
        if (lostInsidePage && lastEditable?.isConnected) {
            focusEditable(lastEditable);
        }
    }, true);
}

installElectronFocusGuard();


const offline = Object.freeze({
    getState: () => ipcRenderer.invoke("offline:get-state"),
    sync: () => ipcRenderer.invoke("offline:sync"),
    submit: payload => ipcRenderer.invoke("offline:submit", payload),
    openOnline: () => ipcRenderer.invoke("offline:open-online"),
    request: payload => ipcRenderer.invoke("offline:request", payload),
    setNetworkState: online => ipcRenderer.invoke("offline:set-network-state", { online: online === true })
});


function installOfflineStatusBadge() {
    if (window.parent !== window) return;

    const create = () => {
        if (document.getElementById("nikaDesktopOfflineBadge")) return;

        const badge = document.createElement("button");
        badge.id = "nikaDesktopOfflineBadge";
        badge.type = "button";
        badge.style.cssText = [
            "position:fixed",
            "right:14px",
            "bottom:14px",
            "z-index:2147483647",
            "display:none",
            "border:0",
            "border-radius:999px",
            "padding:8px 12px",
            "font:700 12px/1.2 Segoe UI,Arial,sans-serif",
            "box-shadow:0 8px 24px rgba(15,23,42,.18)",
            "cursor:pointer",
            "background:#fff7ed",
            "color:#c2410c"
        ].join(";");
        badge.title = "Нажмите, чтобы повторить синхронизацию";
        badge.addEventListener("click", () => {
            ipcRenderer.invoke("offline:sync").catch(() => {});
        });
        document.body.appendChild(badge);

        const update = async () => {
            try {
                const state = await ipcRenderer.invoke("offline:get-state");
                const pending = Number(state?.pending_count || 0);
                const sync = state?.sync_state || "idle";

                if (sync === "synced" && pending === 0) {
                    badge.style.display = "none";
                    return;
                }

                badge.style.display = "block";
                if (sync === "syncing") {
                    badge.textContent = pending
                        ? "Синхронизация · в очереди " + pending
                        : "Синхронизация…";
                    badge.style.background = "#eef2ff";
                    badge.style.color = "#3346a8";
                } else if (pending > 0) {
                    badge.textContent = "Офлайн · в очереди " + pending;
                    badge.style.background = "#fff7ed";
                    badge.style.color = "#c2410c";
                } else {
                    badge.textContent = "Офлайн";
                    badge.style.background = "#fff7ed";
                    badge.style.color = "#c2410c";
                }
            } catch (_) {}
        };

        update();
        window.setInterval(update, 3000);
        window.addEventListener("online", () => {
            ipcRenderer.invoke("offline:sync").catch(() => {});
            update();
        });
        window.addEventListener("offline", update);
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", create, { once: true });
    } else {
        create();
    }
}

function installOfflineFetchBridge() {
    const source = \`
    (() => {
        if (window.__nikaDesktopOfflineFetchInstalled) return;
        window.__nikaDesktopOfflineFetchInstalled = true;
        const originalFetch = window.fetch.bind(window);
        const bridge = window.nikaDesktop && window.nikaDesktop.offline;
        if (!bridge) return;

        const getPaths = new Set([
            "/api/items", "/api/items/search", "/api/stock",
            "/api/stock/movements", "/api/clients",
            "/api/categories", "/api/suppliers", "/api/company/active"
        ]);
        const queuePaths = new Set([
            "/sales/pay", "/api/stock/income", "/api/stock/writeoff",
            "/api/mobile/stock/income/supplier"
        ]);

        function apiLike(pathname) {
            return pathname.startsWith("/api/") ||
                pathname.startsWith("/whatsapp/api/");
        }

        function supported(url, method) {
            if (url.origin !== window.location.origin) return false;
            if (method === "GET") return apiLike(url.pathname);
            if (method === "POST") {
                return queuePaths.has(url.pathname) ||
                    url.pathname === "/api/barcode";
            }
            return false;
        }

        window.fetch = async function(input, init = {}) {
            const request = input instanceof Request ? input : null;
            const method = String(
                init.method || (request && request.method) || "GET"
            ).toUpperCase();
            const inputUrl = request ? request.url : String(input);
            const url = new URL(inputUrl, window.location.href);

            if (!supported(url, method)) {
                if (
                    url.origin === window.location.origin &&
                    apiLike(url.pathname) &&
                    navigator.onLine === false
                ) {
                    throw new TypeError("Failed to fetch");
                }
                return originalFetch(input, init);
            }
            if (init.signal && init.signal.aborted) {
                throw new DOMException("Aborted", "AbortError");
            }

            let bodyText = "";
            if (typeof init.body === "string") {
                bodyText = init.body;
            } else if (request && method !== "GET" && method !== "HEAD") {
                try { bodyText = await request.clone().text(); } catch (_) {}
            }

            try {
                const result = await bridge.request({
                    url: url.pathname + url.search,
                    method,
                    bodyText
                });
                if (!result || result.handled !== true) {
                    return originalFetch(input, init);
                }
                return new Response(result.bodyText || "", {
                    status: Number(result.status || 200),
                    headers: result.headers || {
                        "content-type": "application/json; charset=utf-8"
                    }
                });
            } catch (error) {
                if (error && error.name === "AbortError") throw error;
                return originalFetch(input, init);
            }
        };
    })();
    \`;

    const inject = () => {
        try {
            const script = document.createElement("script");
            script.textContent = source;
            (document.documentElement || document.head || document.body).appendChild(script);
            script.remove();
        } catch (error) {
            console.error("Nika offline fetch bridge install error:", error);
        }
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", inject, { once: true });
    } else {
        inject();
    }
}

function installOfflineNetworkBridge() {
    const report = () => {
        ipcRenderer.invoke("offline:set-network-state", {
            online: navigator.onLine !== false
        }).catch(() => {});
    };
    report();
    window.addEventListener("online", report);
    window.addEventListener("offline", report);
}

const kaspiPos = Object.freeze({
    getState: () => ipcRenderer.invoke("kaspi:get-state"),
    saveIp: (ip) => ipcRenderer.invoke("kaspi:save-ip", { ip }),
    test: (ip) => ipcRenderer.invoke("kaspi:test", { ip }),
    startPayment: (payload) => ipcRenderer.invoke("kaspi:payment", payload || {}),
    getStatus: (processId) => ipcRenderer.invoke("kaspi:status", { processId })
});

const printers = Object.freeze({
    getState: () => ipcRenderer.invoke("printer:get-state"),
    refresh: () => ipcRenderer.invoke("printer:refresh"),
    saveSettings: (settings) =>
        ipcRenderer.invoke("printer:save-settings", settings),
    testReceipt: () => ipcRenderer.invoke("printer:test-receipt"),
    testDocument: () => ipcRenderer.invoke("printer:test-document"),
    printReceipt: (payload) =>
        ipcRenderer.invoke("printer:print-receipt", prepareReceiptPayload(payload)),
    printDocument: (payload) =>
        ipcRenderer.invoke("printer:print-document", payload)
});

contextBridge.exposeInMainWorld("nikaDesktop", Object.freeze({
    isElectron: true,
    platform: process.platform,
    printers,
    kaspiPos,
    offline
}));

installOfflineFetchBridge();
installOfflineNetworkBridge();
installOfflineStatusBadge();
