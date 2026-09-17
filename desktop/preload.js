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
    printers
}));
