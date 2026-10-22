const { app, BrowserWindow, dialog, ipcMain, session, webFrameMain } = require("electron");
const { autoUpdater } = require("electron-updater");
const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");
const http = require("http");

let win;
let flaskProcess;
let updatePromptOpen = false;
let updateCheckTimer;

// The TEST installer contains this file only during the isolated TEST build.
// Production/Legacy installers never include the marker.
const TEST_MODE = fs.existsSync(path.join(__dirname, "nika-electron-test.json")) ||
    process.env.NIKA_ELECTRON_TEST === "1";
const APP_MODE = process.env.NIKA_MODE || "vps";
const DEV_MODE = !TEST_MODE && APP_MODE === "local";
const LEGACY_MODE = !TEST_MODE && (process.env.NIKA_LEGACY === "1" || /legacy/i.test(app.getName()));
const APP_URL = TEST_MODE
    ? "https://test.nikabusiness.com"
    : (DEV_MODE ? "http://127.0.0.1:5000" : "https://nikabusiness.com");
const PERSISTENT_PARTITION = TEST_MODE
    ? "persist:nika-business-test"
    : (LEGACY_MODE ? "persist:nika-business-legacy" : "persist:nika-business");

// Printer preferences, local cookies, sessions and offline cache must never be
// shared with the production Electron installation.
if (TEST_MODE) {
    const testUserData = path.join(app.getPath("appData"), "Nika Business TEST");
    fs.mkdirSync(testUserData, {recursive:true});
    app.setPath("userData", testUserData);
}


// Electron 22/30 on Windows can lose the renderer's IME/character-input
// focus after native JavaScript dialogs. This runs in the MAIN JS world of
// every same-origin frame, including #nikaPageFrame (preload alone does not).
// The native dialog remains synchronous with its original return value.
const NIKA_NATIVE_DIALOG_FOCUS_GUARD = String.raw`(() => {
    if (window.__nikaNativeDialogFocusGuard) return;
    window.__nikaNativeDialogFocusGuard = true;

    ["alert", "confirm", "prompt"].forEach((name) => {
        const original = window[name];
        if (typeof original !== "function") return;
        window[name] = function (...args) {
            try {
                return original.apply(window, args);
            } finally {
                // Notify only AFTER the blocking native dialog is dismissed.
                // A delayed main-process blur/focus repairs Blink's missing
                // IME client, which ordinary element.focus() cannot repair.
                window.setTimeout(() => {
                    try {
                        const host = window.top && window.top.nikaDesktop;
                        if (host && typeof host.recoverKeyboardFocus === "function") {
                            host.recoverKeyboardFocus();
                        }
                    } catch (_) { /* Ignore cross-origin/closed windows. */ }
                }, 40);
            }
        };
    });
})();`;

let focusRecoveryTimer = null;
function registerNativeDialogFocusRecovery() {
    ipcMain.on("nika:recover-keyboard-focus", (event) => {
        if (!win || win.isDestroyed() || event.sender !== win.webContents) return;
        const frameUrl = event.senderFrame && event.senderFrame.url;
        try {
            if (new URL(frameUrl).origin !== new URL(APP_URL).origin) return;
        } catch (_) { return; }
        if (focusRecoveryTimer) clearTimeout(focusRecoveryTimer);
        focusRecoveryTimer = setTimeout(() => {
            focusRecoveryTimer = null;
            // The window often reports isFocused()=false just after a
            // native alert closes, even though the user is still here.
            // Do not skip recovery based on that unreliable flag.
            if (!win || win.isDestroyed() || !win.isVisible() || win.isMinimized()) return;
            win.blur();
            win.focus();
            if (win.webContents && !win.webContents.isDestroyed()) {
                win.webContents.focus();
            }
        }, 30);
    });
}

function installDialogFocusGuard(contents) {
    contents.on("did-frame-finish-load", (_event, _main, processId, routingId) => {
        // WebFrameMain implementations vary between Electron versions.
        // In particular, older builds may not expose isDestroyed().
        // Never let a lifecycle hook throw an uncaught main-process error.
        try {
            const frame = webFrameMain.fromId(processId, routingId);
            if (!frame) return;
            if (typeof frame.isDestroyed === "function" && frame.isDestroyed()) return;
            if (new URL(frame.url).origin !== new URL(APP_URL).origin) return;
            if (typeof frame.executeJavaScript !== "function") return;
            Promise.resolve(frame.executeJavaScript(NIKA_NATIVE_DIALOG_FOCUS_GUARD))
                .catch((error) => {
                    // A frame might navigate away before injection completes.
                    console.warn("Пропуск защиты фокуса при смене страницы:", error.message);
                });
        } catch (error) {
            console.warn("Пропуск защиты фокуса в закрытом frame:", error.message);
        }
    });
}

const DEFAULT_PRINTER_SETTINGS = Object.freeze({
    receipt_printer: null,
    kitchen_printer: null,
    document_printer: null,
    receipt_paper_width: 80,
    receipt_offset_mm: -2,
    receipt_copies: 1,
    kitchen_paper_width: 80,
    kitchen_offset_mm: -2,
    kitchen_copies: 1,
    document_copies: 1,
    auto_print_receipt: false,
    document_landscape: false,
    kaspi_pos_ip: null
});

let settings = { ...DEFAULT_PRINTER_SETTINGS };

function startFlask() {
    flaskProcess = spawn(
        "python",
        ["D:/PRO/nika_business/app.py"],
        {
            cwd: "D:/PRO/nika_business",
            shell: true
        }
    );

    flaskProcess.stdout.on("data", (data) => {
        console.log(`FLASK: ${data}`);
    });

    flaskProcess.stderr.on("data", (data) => {
        console.error(`FLASK ERROR: ${data}`);
    });
}

function printerSettingsPath() {
    return path.join(app.getPath("userData"), "printer-settings.json");
}

function toCopyCount(value) {
    const parsed = Number.parseInt(value, 10);
    if (!Number.isFinite(parsed)) return 1;
    return Math.max(1, Math.min(parsed, 5));
}

function normalizePrinterName(value) {
    if (typeof value !== "string") return null;
    const trimmed = value.trim();
    return trimmed || null;
}

function normalizeKaspiIp(value) {
    if (typeof value !== "string") return null;
    const raw = value.trim()
        .replace(/^https?:\/\//i, "")
        .split("/")[0]
        .split(":")[0];
    const parts = raw.split(".");
    if (parts.length !== 4) return null;

    const octets = parts.map((part) => Number(part));
    if (octets.some((part) => !Number.isInteger(part) || part < 0 || part > 255)) {
        return null;
    }

    const isPrivate =
        octets[0] === 10 ||
        (octets[0] === 172 && octets[1] >= 16 && octets[1] <= 31) ||
        (octets[0] === 192 && octets[1] === 168);

    return isPrivate ? octets.join(".") : null;
}

function normalizeSettings(value = {}) {
    const paperWidth = Number(value.receipt_paper_width);
    const kitchenWidth = Number(value.kitchen_paper_width);
    const rawOffset = Number(value.receipt_offset_mm);
    const rawKitchenOffset = Number(value.kitchen_offset_mm);
    const receiptOffset = Number.isFinite(rawOffset)
        ? Math.max(-5, Math.min(rawOffset, 5))
        : -2;
    return {
        receipt_printer: normalizePrinterName(value.receipt_printer),
        kitchen_printer: normalizePrinterName(value.kitchen_printer),
        document_printer: normalizePrinterName(value.document_printer),
        receipt_paper_width: paperWidth === 58 ? 58 : 80,
        receipt_offset_mm: receiptOffset,
        receipt_copies: toCopyCount(value.receipt_copies),
        kitchen_paper_width: kitchenWidth === 58 ? 58 : 80,
        kitchen_offset_mm: Number.isFinite(rawKitchenOffset)
            ? Math.max(-5, Math.min(rawKitchenOffset, 5)) : -2,
        kitchen_copies: toCopyCount(value.kitchen_copies),
        document_copies: toCopyCount(value.document_copies),
        auto_print_receipt: value.auto_print_receipt === true,
        document_landscape: value.document_landscape === true,
        kaspi_pos_ip: normalizeKaspiIp(value.kaspi_pos_ip)
    };
}

function loadPrinterSettings() {
    try {
        const saved = JSON.parse(
            fs.readFileSync(printerSettingsPath(), "utf8")
        );
        return normalizeSettings({
            ...DEFAULT_PRINTER_SETTINGS,
            ...saved
        });
    } catch (error) {
        if (error.code !== "ENOENT") {
            console.error("Не удалось прочитать настройки принтеров:", error);
        }
        return { ...DEFAULT_PRINTER_SETTINGS };
    }
}

function savePrinterSettings(nextSettings) {
    settings = normalizeSettings({
        ...settings,
        ...nextSettings
    });

    const filePath = printerSettingsPath();
    const tempPath = `${filePath}.tmp`;
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(tempPath, JSON.stringify(settings, null, 2), "utf8");
    fs.renameSync(tempPath, filePath);
    return { ...settings };
}

async function getPrinters() {
    if (!win || win.isDestroyed()) return [];

    const printers = await win.webContents.getPrintersAsync();
    return printers.map((printer) => ({
        name: printer.name,
        displayName: printer.displayName || printer.name,
        description: printer.description || "",
        status: printer.status,
        isDefault: printer.isDefault === true
    }));
}

function isVirtualPrinter(name) {
    return ["PDF", "XPS", "FAX", "ONENOTE"].some((word) =>
        String(name || "").toUpperCase().includes(word)
    );
}

async function detectPrinters() {
    const printers = await getPrinters();
    if (!printers.length) return printers;

    let changed = false;

    if (!settings.receipt_printer) {
        const receiptKeywords = [
            "POS", "POS58", "POS80", "XPRINTER", "XP-",
            "THERMAL", "RECEIPT", "MHT", "MILESTONE"
        ];
        const receiptPrinter = printers.find((printer) =>
            receiptKeywords.some((keyword) =>
                printer.name.toUpperCase().includes(keyword)
            )
        );

        if (receiptPrinter) {
            settings.receipt_printer = receiptPrinter.name;
            changed = true;
        }
    }

    if (!settings.document_printer) {
        const documentPrinter = printers.find((printer) =>
            printer.name !== settings.receipt_printer &&
            !isVirtualPrinter(printer.name)
        );

        if (documentPrinter) {
            settings.document_printer = documentPrinter.name;
            changed = true;
        }
    }

    if (changed) savePrinterSettings(settings);

    console.log("Найдены принтеры:");
    printers.forEach((printer) => console.log(printer.name));
    return printers;
}

function requireMainWindow(event) {
    if (!win || win.isDestroyed() || event.sender !== win.webContents) {
        throw new Error("Команда доступна только из окна Nika Business");
    }
}

async function getPrinterState() {
    const printers = await getPrinters();
    const names = new Set(printers.map((printer) => printer.name));
    return {
        isElectron: true,
        printers,
        settings: { ...settings },
        availability: {
            receipt: settings.receipt_printer
                ? names.has(settings.receipt_printer)
                : false,
            kitchen: settings.kitchen_printer
                ? names.has(settings.kitchen_printer)
                : false,
            document: settings.document_printer
                ? names.has(settings.document_printer)
                : false
        }
    };
}

function ensureSelectedPrinter(deviceName, kind) {
    if (!deviceName) {
        throw new Error(
            kind === "kitchen"
                ? "Сначала выберите принтер кухни в настройках"
                : kind === "receipt"
                    ? "Сначала выберите чековый принтер в настройках"
                    : "Сначала выберите принтер документов в настройках"
        );
    }
}

function receiptPage(html, title = "Чек", paper = {}) {
    const paperWidth = paper.width === 58 ? 58 : paper.width === 80 ? 80
        : (settings.receipt_paper_width === 58 ? 58 : 80);
    // У принтеров с лентой 80 мм реальная печатная область обычно 68–72 мм.
    // Берём безопасную ширину, чтобы правый край не обрезался драйвером.
    const contentWidth = paperWidth === 58 ? 48 : 68;
    const baseSideMargin = (paperWidth - contentWidth) / 2;
    const offset = Number(paper.offset ?? settings.receipt_offset_mm ?? 0);
    const leftMargin = Math.max(0, baseSideMargin + offset);
    const rightMargin = Math.max(
        0,
        paperWidth - contentWidth - leftMargin
    );
    return `<!doctype html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>${title}</title>
    <style>
        @page { margin: 0; }
        * { box-sizing: border-box; }
        html, body {
            width: ${paperWidth}mm;
            max-width: ${paperWidth}mm;
            margin: 0;
            padding: 0;
            overflow: visible;
            background: #fff;
            color: #111;
        }
        body {
            min-width: 0;
            -webkit-print-color-adjust: exact;
            print-color-adjust: exact;
        }
        .receipt,
        .shift-report-paper {
            width: ${contentWidth}mm !important;
            max-width: ${contentWidth}mm !important;
            min-height: 0 !important;
            margin: 0 ${rightMargin}mm 0 ${leftMargin}mm !important;
            padding: 1.5mm 0 !important;
            overflow: visible !important;
            background: #fff !important;
            color: #000 !important;
        }
        img { max-width: 100%; }
    </style>
</head>
<body>
${html}
<style>
    @page { margin: 0 !important; }
    html, body {
        width: ${paperWidth}mm !important;
        max-width: ${paperWidth}mm !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    .receipt,
    .shift-report-paper {
        width: ${contentWidth}mm !important;
        max-width: ${contentWidth}mm !important;
        min-height: 0 !important;
        margin: 0 ${rightMargin}mm 0 ${leftMargin}mm !important;
        padding: 1.5mm 0 !important;
        overflow: visible !important;
        background: #fff !important;
        color: #000 !important;
    }
    .receipt *,
    .shift-report-paper * { box-sizing: border-box; }
    .receipt .info-row,
    .receipt .item-meta,
    .receipt .payment,
    .receipt .total,
    .receipt .row {
        min-width: 0 !important;
        gap: 5px !important;
    }
    .receipt .info-row > :first-child,
    .receipt .item-meta > :first-child,
    .receipt .payment > :first-child,
    .receipt .total > :first-child,
    .receipt .row > :first-child {
        min-width: 0 !important;
        overflow-wrap: anywhere !important;
    }
    .receipt .info-row > :last-child,
    .receipt .item-meta > :last-child,
    .receipt .payment > :last-child,
    .receipt .total > :last-child,
    .receipt .row > :last-child {
        flex: 0 1 auto !important;
        min-width: 0 !important;
        text-align: right !important;
        overflow-wrap: anywhere !important;
    }
    .shift-report-paper {
        font-family: Arial, Helvetica, sans-serif !important;
        font-size: 12px !important;
        font-weight: 600 !important;
        line-height: 1.32 !important;
        box-shadow: none !important;
    }
    .shift-receipt-center { text-align: center !important; }
    .shift-receipt-name { font-size: 16px !important; font-weight: 800 !important; }
    .shift-receipt-id { font-size: 12px !important; font-weight: 700 !important; }
    .shift-receipt-address { margin-top: 2px !important; font-size: 11px !important; font-weight: 600 !important; }
    .shift-receipt-requisites { margin: 12px 0 !important; }
    .shift-receipt-line {
        display: flex !important;
        justify-content: space-between !important;
        align-items: flex-start !important;
        gap: 6px !important;
        margin: 3px 0 !important;
    }
    .shift-receipt-line > :first-child { min-width: 0 !important; overflow-wrap: anywhere !important; }
    .shift-receipt-line > :last-child { flex: 0 0 auto !important; text-align: right !important; font-weight: 700 !important; }
    .shift-receipt-kind { margin: 14px 0 12px !important; text-align: center !important; font-size: 18px !important; font-weight: 900 !important; }
    .shift-receipt-grid {
        display: grid !important;
        grid-template-columns: auto 1fr !important;
        gap: 3px 8px !important;
        align-items: baseline !important;
    }
    .shift-receipt-grid .value { text-align: right !important; white-space: normal !important; font-weight: 700 !important; }
    .shift-receipt-separator { margin: 10px 0 !important; border-top: 1px dashed #000 !important; }
    .shift-receipt-section-title { margin: 0 0 5px !important; font-size: 13px !important; font-weight: 900 !important; text-transform: uppercase !important; }
    .shift-receipt-block { margin: 0 0 11px !important; }
    .shift-receipt-operation-title { margin: 0 0 4px !important; font-size: 14px !important; font-weight: 900 !important; text-transform: uppercase !important; }
    .shift-receipt-total-count { margin-top: 10px !important; }
    .shift-receipt-fdo { margin-top: 16px !important; text-align: center !important; font-size: 11px !important; font-weight: 700 !important; }
    .shift-receipt-empty { color: #000 !important; text-align: center !important; }
</style>
</body>
</html>`;
}

function documentPage(html, title = "Документ", landscape = false) {
    const pageSize = landscape ? "A4 landscape" : "A4";
    const printStyle = `
        <style>
            @page { size: ${pageSize}; margin: 10mm; }
            html, body { margin: 0; padding: 0; background: #fff; }
        </style>`;

    if (/<html[\s>]/i.test(html)) {
        if (/<\/head>/i.test(html)) {
            return html.replace(/<\/head>/i, `${printStyle}</head>`);
        }
        return html.replace(/<html([^>]*)>/i, `<html$1><head>${printStyle}</head>`);
    }

    return `<!doctype html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>${title}</title>
    ${printStyle}
</head>
<body>${html}</body>
</html>`;
}

function waitForPrint(printWindow, options) {
    return new Promise((resolve, reject) => {
        printWindow.webContents.print(options, (success, failureReason) => {
            if (success) resolve({ success: true });
            else reject(new Error(failureReason || "Windows не принял задание печати"));
        });
    });
}

async function printHtml({ html, title, kind, landscape }) {
    if (typeof html !== "string" || !html.trim()) {
        throw new Error("Нет содержимого для печати");
    }
    if (html.length > 5_000_000) {
        throw new Error("Документ слишком большой для печати");
    }

    const kitchen = kind === "kitchen";
    const receipt = kind === "receipt" || kitchen;
    const deviceName = kitchen ? settings.kitchen_printer
        : receipt ? settings.receipt_printer : settings.document_printer;
    ensureSelectedPrinter(deviceName, kind);

    const printers = await getPrinters();
    if (!printers.some((printer) => printer.name === deviceName)) {
        throw new Error(`Принтер «${deviceName}» сейчас не найден в Windows`);
    }

    const printWindow = new BrowserWindow({
        show: false,
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            partition: PERSISTENT_PARTITION
        }
    });

    try {
        const page = receipt
            ? receiptPage(html, title, kitchen
                ? {width: settings.kitchen_paper_width, offset: settings.kitchen_offset_mm}
                : {width: settings.receipt_paper_width, offset: settings.receipt_offset_mm})
            : documentPage(
                html,
                title,
                typeof landscape === "boolean"
                    ? landscape
                    : settings.document_landscape
            );
        const dataUrl = `data:text/html;base64,${Buffer.from(page, "utf8").toString("base64")}`;

        await printWindow.loadURL(dataUrl);
        await printWindow.webContents.executeJavaScript(`
            Promise.all(Array.from(document.images).map((image) => {
                if (image.complete) return true;
                return new Promise((resolve) => {
                    image.addEventListener("load", () => resolve(true), { once: true });
                    image.addEventListener("error", () => resolve(true), { once: true });
                    setTimeout(() => resolve(true), 4000);
                });
            }))
        `);

        const options = {
            silent: true,
            printBackground: true,
            deviceName,
            copies: kitchen ? settings.kitchen_copies
                : receipt ? settings.receipt_copies : settings.document_copies,
            margins: { marginType: "none" }
        };

        if (!receipt) {
            options.pageSize = "A4";
            options.landscape = typeof landscape === "boolean"
                ? landscape
                : settings.document_landscape;
        }

        return await waitForPrint(printWindow, options);
    } finally {
        if (!printWindow.isDestroyed()) printWindow.destroy();
    }
}

function testReceiptHtml() {
    const now = new Intl.DateTimeFormat("ru-RU", {
        dateStyle: "short",
        timeStyle: "short"
    }).format(new Date());
    return `
        <main class="receipt" style="font:12px/1.35 'Courier New',monospace;color:#111">
            <div style="text-align:center;font-size:17px;font-weight:700">NIKA BUSINESS</div>
            <div style="text-align:center">Тест чекового принтера</div>
            <div style="margin:8px 0;border-top:1px dashed #111"></div>
            <div style="display:flex;justify-content:space-between"><span>Дата</span><span>${now}</span></div>
            <div style="display:flex;justify-content:space-between"><span>Ширина ленты</span><span>${settings.receipt_paper_width} мм</span></div>
            <div style="display:flex;justify-content:space-between"><span>Рабочая ширина</span><span>${settings.receipt_paper_width === 58 ? 48 : 68} мм</span></div>
            <div style="display:flex;justify-content:space-between"><span>Смещение</span><span>${settings.receipt_offset_mm} мм</span></div>
            <div style="display:flex;justify-content:space-between"><span>Копий</span><span>${settings.receipt_copies}</span></div>
            <div style="margin:8px 0;border-top:1px dashed #111"></div>
            <div>Русский: Проверка печати</div>
            <div>Қазақша: Басып шығаруды тексеру</div>
            <div style="margin-top:10px;text-align:center;font-weight:700">ПРИНТЕР НАСТРОЕН</div>
        </main>`;
}

function testDocumentHtml() {
    return `
        <main style="font-family:Arial,sans-serif;color:#182033">
            <h1 style="margin:0 0 10px">Nika Business</h1>
            <h2>Тест печати документа</h2>
            <p>Если этот лист распечатан, принтер документов настроен правильно.</p>
            <p>Русский и қазақша мәтін отображаются через драйвер Windows.</p>
        </main>`;
}

function kaspiPosRequest(pathname, params = {}, options = {}) {
    const ip = normalizeKaspiIp(options.ip || settings.kaspi_pos_ip);
    if (!ip) {
        return Promise.reject(new Error("Укажите IP Kaspi POS в Настройки → POS терминалы"));
    }

    const query = new URLSearchParams();
    Object.entries(params || {}).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== "") {
            query.set(key, String(value));
        }
    });

    const suffix = query.toString() ? `?${query.toString()}` : "";
    const target = `http://${ip}:8080${pathname}${suffix}`;
    const timeoutMs = Number(options.timeoutMs || 7000);

    return new Promise((resolve, reject) => {
        const request = http.get(target, { timeout: timeoutMs }, (response) => {
            let body = "";
            response.setEncoding("utf8");
            response.on("data", (chunk) => {
                body += chunk;
                if (body.length > 1024 * 1024) {
                    request.destroy(new Error("Слишком большой ответ Kaspi POS"));
                }
            });
            response.on("end", () => {
                let data;
                try {
                    data = body ? JSON.parse(body) : {};
                } catch (_) {
                    reject(new Error("Kaspi POS вернул некорректный ответ"));
                    return;
                }
                resolve({
                    httpStatus: response.statusCode || 0,
                    data
                });
            });
        });

        request.on("timeout", () => {
            request.destroy(new Error("Kaspi POS не отвечает. Проверьте IP и локальную сеть"));
        });
        request.on("error", reject);
    });
}

async function kaspiPosTest(ipOverride = null) {
    const ip = normalizeKaspiIp(ipOverride || settings.kaspi_pos_ip);
    if (!ip) {
        return {
            success: false,
            connected: false,
            error: "Некорректный локальный IP терминала"
        };
    }

    try {
        const response = await kaspiPosRequest("/v2/deviceinfo", {}, {
            ip,
            timeoutMs: 4500
        });
        const connected =
            response.httpStatus >= 200 &&
            response.httpStatus < 300;

        return {
            success: connected,
            connected,
            ip,
            httpStatus: response.httpStatus,
            device: response.data
        };
    } catch (error) {
        return {
            success: false,
            connected: false,
            ip,
            error: error.message || String(error)
        };
    }
}

function registerKaspiPosIpc() {
    ipcMain.handle("kaspi:get-state", async (event) => {
        requireMainWindow(event);
        return {
            isElectron: true,
            ip: settings.kaspi_pos_ip || "",
            configured: Boolean(settings.kaspi_pos_ip)
        };
    });

    ipcMain.handle("kaspi:save-ip", async (event, payload = {}) => {
        requireMainWindow(event);
        const ip = normalizeKaspiIp(payload.ip);
        if (!ip) {
            return {
                success: false,
                error: "Введите локальный IP, например 192.168.1.159"
            };
        }
        savePrinterSettings({ kaspi_pos_ip: ip });
        return { success: true, ip };
    });

    ipcMain.handle("kaspi:test", async (event, payload = {}) => {
        requireMainWindow(event);
        return kaspiPosTest(payload.ip || null);
    });

    ipcMain.handle("kaspi:payment", async (event, payload = {}) => {
        requireMainWindow(event);
        if (TEST_MODE) {
            return {success:false, error:"Kaspi POS отключён в тестовой сборке: реальное списание денег запрещено"};
        }
        const amount = Math.round(Number(payload.amount || 0));
        if (!Number.isFinite(amount) || amount <= 0) {
            return { success: false, error: "Некорректная сумма оплаты" };
        }

        try {
            const response = await kaspiPosRequest(
                "/v2/payment",
                { amount },
                { timeoutMs: 10000 }
            );
            const result = response.data || {};

            if (
                response.httpStatus < 200 ||
                response.httpStatus >= 300 ||
                result.statusCode !== 0
            ) {
                return {
                    success: false,
                    error: result,
                    httpStatus: response.httpStatus
                };
            }

            const processId =
                result &&
                result.data &&
                result.data.processId;

            if (!processId) {
                return {
                    success: false,
                    error: "Kaspi POS не вернул processId"
                };
            }

            return { success: true, processId, raw: result };
        } catch (error) {
            return {
                success: false,
                error: error.message || String(error)
            };
        }
    });

    ipcMain.handle("kaspi:refund", async (event, payload = {}) => {
        requireMainWindow(event);
        if (TEST_MODE) {
            return {success:false, error:"Kaspi POS отключён в тестовой сборке: реальный возврат денег запрещён"};
        }

        const transactionId = String(payload.transactionId || "").trim();
        const method = String(payload.method || "qr").trim() || "qr";
        const amount = Math.round(Number(payload.amount || 0));

        if (!transactionId) {
            return { success: false, error: "transactionId не указан" };
        }
        if (!Number.isFinite(amount) || amount <= 0) {
            return { success: false, error: "Некорректная сумма возврата" };
        }

        try {
            const response = await kaspiPosRequest(
                "/v2/refund",
                { transactionId, amount, method },
                { timeoutMs: 15000 }
            );
            const result = response.data || {};

            if (
                response.httpStatus < 200 ||
                response.httpStatus >= 300 ||
                result.statusCode !== 0
            ) {
                return {
                    success: false,
                    error: result,
                    httpStatus: response.httpStatus
                };
            }

            const processId =
                result &&
                result.data &&
                result.data.processId;

            if (!processId) {
                return {
                    success: false,
                    error: "Kaspi POS не вернул processId возврата"
                };
            }

            return { success: true, processId, raw: result };
        } catch (error) {
            return {
                success: false,
                error: error.message || String(error)
            };
        }
    });

    ipcMain.handle("kaspi:status", async (event, payload = {}) => {
        requireMainWindow(event);
        const processId = String(payload.processId || "").trim();
        if (!processId) {
            return { status: "error", message: "processId не указан" };
        }

        try {
            const response = await kaspiPosRequest(
                "/v2/status",
                { processId },
                { timeoutMs: 7000 }
            );
            const result = response.data || {};
            const data = result.data || {};
            const chequeInfo = data.chequeInfo || {};

            return {
                status: data.status,
                subStatus: data.subStatus,
                message: data.message,
                transactionId: data.transactionId,
                method: chequeInfo.method,
                raw: result
            };
        } catch (error) {
            return {
                status: "error",
                message: error.message || String(error)
            };
        }
    });
}


// One user action queues both documents. A persistent-in-process success set
// prevents a failed kitchen job from reprinting an already accepted guest job.
// These keys refer only to printer spool acceptance, not physical paper output.
const acceptedFoodPrints = new Map();
let foodPrintQueue = Promise.resolve();
function printFoodOrderBatch(payload = {}) {
    const operation = foodPrintQueue.then(async () => {
        const id = Number(payload.orderId);
        const fingerprint = String(payload.fingerprint || "");
        if (!Number.isSafeInteger(id) || id <= 0 || fingerprint.length < 8 ||
            fingerprint.length > 200000) {
            throw new Error("Неверный идентификатор или состав заказа общепита");
        }
        const key = id + ":" + fingerprint;
        const prior = acceptedFoodPrints.get(key) || {guest:false, kitchen:false};
        const results = {};
        for (const [label, field, kind, title] of [
            ["guest", "guestHtml", "receipt", "Пречек гостю №" + id],
            ["kitchen", "kitchenHtml", "kitchen", "Заказ на кухню №" + id]
        ]) {
            if (prior[label]) {
                results[label] = {success:true, alreadySent:true};
                continue;
            }
            try {
                await printHtml({html: payload[field], title, kind});
                prior[label] = true;
                results[label] = {success:true, alreadySent:false};
            } catch (error) {
                results[label] = {success:false, error:error.message || String(error)};
            }
        }
        acceptedFoodPrints.set(key, prior);
        // Prevent unbounded growth on a permanently running checkout device.
        if (acceptedFoodPrints.size > 200) {
            acceptedFoodPrints.delete(acceptedFoodPrints.keys().next().value);
        }
        return {
            success: results.guest.success && results.kitchen.success,
            guest: results.guest,
            kitchen: results.kitchen
        };
    });
    foodPrintQueue = operation.then(() => {}, () => {});
    return operation;
}

function registerPrinterIpc() {
    ipcMain.handle("printer:get-state", async (event) => {
        requireMainWindow(event);
        return getPrinterState();
    });

    ipcMain.handle("printer:refresh", async (event) => {
        requireMainWindow(event);
        await detectPrinters();
        return getPrinterState();
    });

    ipcMain.handle("printer:save-settings", async (event, data) => {
        requireMainWindow(event);
        const saved = savePrinterSettings(data || {});
        return { success: true, settings: saved };
    });

    ipcMain.handle("printer:test-receipt", async (event) => {
        requireMainWindow(event);
        return printHtml({
            html: testReceiptHtml(),
            title: "Тест чекового принтера",
            kind: "receipt"
        });
    });

    ipcMain.handle("printer:test-kitchen", async (event) => {
        requireMainWindow(event);
        return printHtml({
            html: '<div style="font:700 16px Arial;text-align:center">ТЕСТ КУХНИ</div><hr><p>Тестовый заказ №001</p><p>Шаурма × 1</p><strong>Без лука</strong>',
            title: "Тест кухонного принтера",
            kind: "kitchen"
        });
    });

    ipcMain.handle("printer:print-food-order", async (event, payload = {}) => {
        requireMainWindow(event);
        return printFoodOrderBatch(payload);
    });

    ipcMain.handle("printer:test-document", async (event) => {
        requireMainWindow(event);
        return printHtml({
            html: testDocumentHtml(),
            title: "Тест принтера документов",
            kind: "document"
        });
    });

    ipcMain.handle("printer:print-receipt", async (event, payload = {}) => {
        requireMainWindow(event);
        return printHtml({
            html: payload.html,
            title: payload.title || "Чек",
            kind: "receipt"
        });
    });

    ipcMain.handle("printer:print-document", async (event, payload = {}) => {
        requireMainWindow(event);
        return printHtml({
            html: payload.html,
            title: payload.title || "Документ",
            kind: "document",
            landscape: typeof payload.landscape === "boolean"
                ? payload.landscape
                : undefined
        });
    });

    // Совместимость с уже установленными версиями сайта.
    ipcMain.on("set-printers", (event, data) => {
        try {
            requireMainWindow(event);
            savePrinterSettings(data || {});
        } catch (error) {
            console.error("Не удалось сохранить принтеры:", error);
        }
    });

    ipcMain.on("print-receipt", (event) => {
        try {
            requireMainWindow(event);
            ensureSelectedPrinter(settings.receipt_printer, "receipt");
            win.webContents.print({
                silent: true,
                printBackground: true,
                deviceName: settings.receipt_printer,
                copies: settings.receipt_copies
            });
        } catch (error) {
            console.error("Не удалось распечатать чек:", error);
        }
    });

    ipcMain.on("print-document", (event) => {
        try {
            requireMainWindow(event);
            ensureSelectedPrinter(settings.document_printer, "document");
            win.webContents.print({
                silent: true,
                printBackground: true,
                deviceName: settings.document_printer,
                copies: settings.document_copies,
                pageSize: "A4",
                landscape: settings.document_landscape
            });
        } catch (error) {
            console.error("Не удалось распечатать документ:", error);
        }
    });
}

async function clearRetiredDesktopOfflineState() {
    const marker = path.join(app.getPath("userData"), "desktop-offline-retired-v1");
    if (fs.existsSync(marker)) return;

    const ses = session.fromPartition(PERSISTENT_PARTITION);

    try {
        await ses.clearStorageData({
            storages: ["serviceworkers", "cachestorage"]
        });
        await ses.clearCache();
        fs.writeFileSync(marker, new Date().toISOString(), "utf8");
        console.log("Старый desktop offline cache очищен");
    } catch (error) {
        console.error("Не удалось очистить старый desktop offline cache:", error);
    }
}

function createWindow() {
    win = new BrowserWindow({
        width: 1400,
        height: 900,
        backgroundColor: "#f4f7fb",
        title: TEST_MODE ? "Nika Business TEST" : "Nika Business",
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            spellcheck: false,
            preload: path.join(__dirname, "preload.js"),
            partition: PERSISTENT_PARTITION
        }
    });

    installDialogFocusGuard(win.webContents);
    if (DEV_MODE) setTimeout(() => win.loadURL(APP_URL), 5000);
    else win.loadURL(APP_URL);

    if (TEST_MODE) {
        win.webContents.on("page-title-updated", (event) => {
            event.preventDefault();
            win.setTitle("Nika Business TEST — test.nikabusiness.com");
        });
    }
    win.maximize();
    win.setMenu(null);

    win.webContents.once("did-finish-load", async () => {
        try {
            await detectPrinters();
        } catch (error) {
            console.error("Не удалось получить список принтеров:", error);
        }
    });

    win.on("closed", () => {
        win = null;
    });
}

function configureAutoUpdates() {
    if (TEST_MODE) {
        console.log("Тестовый Electron: обновления рабочей версии отключены");
        return;
    }
    if (!app.isPackaged) {
        console.log("Автообновление отключено в режиме разработки");
        return;
    }

    autoUpdater.autoDownload = false;
    autoUpdater.autoInstallOnAppQuit = true;
    autoUpdater.allowDowngrade = false;
    if (LEGACY_MODE) {
        // Windows 8.1 must remain on the Electron 22-compatible release line.
        autoUpdater.channel = "legacy";
        autoUpdater.allowPrerelease = false;
    }
    // The GitHub feed is embedded into app-update.yml by electron-builder
    // from package.json. electron-updater reads latest.yml from the newest
    // published GitHub Release; setFeedURL must not be called here.

    autoUpdater.on("update-available", async (info) => {
        if (updatePromptOpen || !win || win.isDestroyed()) return;
        updatePromptOpen = true;
        try {
            const result = await dialog.showMessageBox(win, {
                type: "info",
                title: "Обновление Nika Business",
                message: `Доступна новая версия ${info.version}`,
                detail: "Скачать обновление сейчас? Можно продолжать работу, пока оно загружается.",
                buttons: ["Обновить", "Позже"],
                defaultId: 0,
                cancelId: 1,
                noLink: true
            });
            if (result.response === 0) {
                await autoUpdater.downloadUpdate();
            }
        } catch (error) {
            console.error("Не удалось скачать обновление:", error);
        } finally {
            updatePromptOpen = false;
        }
    });

    autoUpdater.on("update-downloaded", async (info) => {
        if (!win || win.isDestroyed()) return;
        const result = await dialog.showMessageBox(win, {
            type: "info",
            title: "Обновление готово",
            message: `Nika Business ${info.version} скачана`,
            detail: "Перезапустить приложение и установить обновление?",
            buttons: ["Перезапустить сейчас", "После закрытия приложения"],
            defaultId: 0,
            cancelId: 1,
            noLink: true
        });
        if (result.response === 0) {
            setImmediate(() => autoUpdater.quitAndInstall(false, true));
        }
    });

    autoUpdater.on("error", (error) => {
        console.error("Ошибка автообновления Nika Business:", error);
    });

    const check = () => autoUpdater.checkForUpdates().catch((error) => {
        console.error("Не удалось проверить обновления:", error);
    });

    setTimeout(check, 10_000);
    updateCheckTimer = setInterval(check, 4 * 60 * 60 * 1000);
}

app.whenReady().then(async () => {
    settings = loadPrinterSettings();
    registerPrinterIpc();
    registerKaspiPosIpc();
    registerNativeDialogFocusRecovery();
    await clearRetiredDesktopOfflineState();
    if (DEV_MODE) startFlask();
    createWindow();
    configureAutoUpdates();

    app.on("activate", () => {
        if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
});

app.on("window-all-closed", () => {
    if (updateCheckTimer) clearInterval(updateCheckTimer);
    if (focusRecoveryTimer) clearTimeout(focusRecoveryTimer);
    if (DEV_MODE && flaskProcess) {
        flaskProcess.kill();
        flaskProcess = null;
    }
    if (process.platform !== "darwin") app.quit();
});
