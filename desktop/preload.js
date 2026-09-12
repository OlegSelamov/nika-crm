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
