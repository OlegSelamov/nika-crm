const { app, BrowserWindow, ipcMain } = require("electron");
const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");

let win;
let flaskProcess;

const APP_MODE = process.env.NIKA_MODE || "vps";
const DEV_MODE = APP_MODE === "local";
const APP_URL = DEV_MODE
    ? "http://127.0.0.1:5000"
    : "https://nikabusiness.com";

const DEFAULT_PRINTER_SETTINGS = Object.freeze({
    receipt_printer: null,
    document_printer: null,
    receipt_paper_width: 80,
    receipt_copies: 1,
    document_copies: 1,
    auto_print_receipt: false,
    document_landscape: false
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

function normalizeSettings(value = {}) {
    const paperWidth = Number(value.receipt_paper_width);
    return {
        receipt_printer: normalizePrinterName(value.receipt_printer),
        document_printer: normalizePrinterName(value.document_printer),
        receipt_paper_width: paperWidth === 58 ? 58 : 80,
        receipt_copies: toCopyCount(value.receipt_copies),
        document_copies: toCopyCount(value.document_copies),
        auto_print_receipt: value.auto_print_receipt === true,
        document_landscape: value.document_landscape === true
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
            document: settings.document_printer
                ? names.has(settings.document_printer)
                : false
        }
    };
}

function ensureSelectedPrinter(deviceName, kind) {
    if (!deviceName) {
        throw new Error(
            kind === "receipt"
                ? "Сначала выберите чековый принтер в настройках"
                : "Сначала выберите принтер документов в настройках"
        );
    }
}

function receiptPage(html, title = "Чек") {
    const paperWidth = settings.receipt_paper_width === 58 ? 58 : 80;
    // У принтеров с лентой 80 мм реальная печатная область обычно 68–72 мм.
    // Берём безопасную ширину, чтобы правый край не обрезался драйвером.
    const contentWidth = paperWidth === 58 ? 48 : 68;
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
            width: 100%;
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
            margin: 0 auto !important;
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
    html, body { width: 100% !important; margin: 0 !important; padding: 0 !important; }
    .receipt,
    .shift-report-paper {
        width: ${contentWidth}mm !important;
        max-width: ${contentWidth}mm !important;
        min-height: 0 !important;
        margin: 0 auto !important;
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

function documentPage(html, title = "Документ") {
    const printStyle = `
        <style>
            @page { size: A4; margin: 10mm; }
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

async function printHtml({ html, title, kind }) {
    if (typeof html !== "string" || !html.trim()) {
        throw new Error("Нет содержимого для печати");
    }
    if (html.length > 5_000_000) {
        throw new Error("Документ слишком большой для печати");
    }

    const receipt = kind === "receipt";
    const deviceName = receipt
        ? settings.receipt_printer
        : settings.document_printer;
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
            partition: "persist:nika-business"
        }
    });

    try {
        const page = receipt
            ? receiptPage(html, title)
            : documentPage(html, title);
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
            copies: receipt
                ? settings.receipt_copies
                : settings.document_copies,
            margins: { marginType: "none" }
        };

        if (!receipt) {
            options.pageSize = "A4";
            options.landscape = settings.document_landscape;
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
            kind: "document"
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

function createWindow() {
    win = new BrowserWindow({
        width: 1400,
        height: 900,
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            preload: path.join(__dirname, "preload.js"),
            partition: "persist:nika-business"
        }
    });

    if (DEV_MODE) setTimeout(() => win.loadURL(APP_URL), 5000);
    else win.loadURL(APP_URL);

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

app.whenReady().then(() => {
    settings = loadPrinterSettings();
    registerPrinterIpc();
    if (DEV_MODE) startFlask();
    createWindow();

    app.on("activate", () => {
        if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
});

app.on("window-all-closed", () => {
    if (DEV_MODE && flaskProcess) {
        flaskProcess.kill();
        flaskProcess = null;
    }
    if (process.platform !== "darwin") app.quit();
});
