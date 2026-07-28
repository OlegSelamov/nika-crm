const { app, BrowserWindow, ipcMain } = require('electron');

const path = require('path');

const { spawn } = require('child_process');

let win;
let flaskProcess;

const APP_MODE = process.env.NIKA_MODE || "vps";
const DEV_MODE = APP_MODE === "local";

const APP_URL = DEV_MODE
    ? "http://127.0.0.1:5000"
    : "https://nikabusiness.com";

function startFlask() {

    flaskProcess = spawn(

        'python',

        ['D:/PRO/nika_business/app.py'],

        {
            cwd: 'D:/PRO/nika_business',
            shell: true
        }
    );

    flaskProcess.stdout.on('data', (data) => {
        console.log(`FLASK: ${data}`);
    });

    flaskProcess.stderr.on('data', (data) => {
        console.error(`FLASK ERROR: ${data}`);
    });
}

function createWindow() {

    win = new BrowserWindow({

        width: 1400,
        height: 900,

        webPreferences: {
            nodeIntegration: true,
            contextIsolation: false,
			partition: "persist:nika-business"
        }

    });

	if (DEV_MODE) {

		setTimeout(() => {
			win.loadURL(APP_URL);
		}, 5000);

	} else {

		win.loadURL(APP_URL);

	}

	win.maximize();

	win.setMenu(null);

	win.webContents.once('did-finish-load', async () => {

		const printers =
			await win.webContents.getPrintersAsync();

		console.log("ПРИНТЕРЫ:");

		printers.forEach(p => {
			console.log(p.name);
		});

	});
}

app.whenReady().then(async () => {

    if (DEV_MODE) {
        startFlask();
    }

    createWindow();

    setTimeout(async () => {
        await detectPrinters();
    }, DEV_MODE ? 7000 : 2000);

});

let settings = {
    receipt_printer: null,
    document_printer: null
};

async function detectPrinters() {

    const printers =
        await win.webContents.getPrintersAsync();

    console.log("Найдены принтеры:");

    printers.forEach(p => {
        console.log(p.name);
    });

    const receiptKeywords = [
        "POS",
        "POS58",
        "XPrinter",
        "XP-",
        "Thermal",
        "Receipt"
    ];

    const receiptPrinter = printers.find(p =>

        receiptKeywords.some(k =>
            p.name.toLowerCase().includes(
                k.toLowerCase()
            )
        )

    );

    if (receiptPrinter) {

        settings.receipt_printer =
            receiptPrinter.name;

        console.log(
            "Чековый принтер:",
            receiptPrinter.name
        );
    }

    const documentPrinter = printers.find(p =>

        p.name !== settings.receipt_printer &&

        !p.name.includes("PDF") &&
        !p.name.includes("XPS") &&
        !p.name.includes("Fax") &&
        !p.name.includes("OneNote")

    );

    if (documentPrinter) {

        settings.document_printer =
            documentPrinter.name;

        console.log(
            "Документный принтер:",
            documentPrinter.name
        );
    }

}

ipcMain.on('set-printers', (event, data) => {

    settings.receipt_printer = data.receipt_printer;
    settings.document_printer = data.document_printer;

});

ipcMain.on('print-receipt', () => {

    console.log("PRINT RECEIPT EVENT");

    win.webContents.print({

        silent: true,
        printBackground: true,
        deviceName: settings.receipt_printer

    });

});


ipcMain.on('print-document', () => {

    win.webContents.print({

        silent: true,
        printBackground: true,

        deviceName:
            settings.document_printer || undefined

    });

});

app.on('window-all-closed', () => {

	if (DEV_MODE && flaskProcess) {
		flaskProcess.kill();
	}

    app.quit();
});