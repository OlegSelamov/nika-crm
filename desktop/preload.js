const { contextBridge, ipcRenderer } = require("electron");

const printers = Object.freeze({
    getState: () => ipcRenderer.invoke("printer:get-state"),
    refresh: () => ipcRenderer.invoke("printer:refresh"),
    saveSettings: (settings) =>
        ipcRenderer.invoke("printer:save-settings", settings),
    testReceipt: () => ipcRenderer.invoke("printer:test-receipt"),
    testDocument: () => ipcRenderer.invoke("printer:test-document"),
    printReceipt: (payload) =>
        ipcRenderer.invoke("printer:print-receipt", payload),
    printDocument: (payload) =>
        ipcRenderer.invoke("printer:print-document", payload)
});

contextBridge.exposeInMainWorld("nikaDesktop", Object.freeze({
    isElectron: true,
    platform: process.platform,
    printers
}));
