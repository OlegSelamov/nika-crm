const { app, BrowserWindow } = require("electron");
const path = require("path");
const { exec } = require("child_process");

let flaskProcess;

function createWindow() {

    const win = new BrowserWindow({

        width: 1400,
        height: 900,

        webPreferences: {
            nodeIntegration: false
        }

    });

    win.loadURL("http://127.0.0.1:5000");
}

app.whenReady().then(() => {

    // 🔥 запуск Flask
    flaskProcess = exec(
        "start.bat",
        {
            cwd: path.join(__dirname)
        }
    );

    // ждём запуск сервера
    setTimeout(() => {

        createWindow();

    }, 3000);

});

app.on("window-all-closed", () => {

    if (flaskProcess) {
        flaskProcess.kill();
    }

    if (process.platform !== "darwin") {
        app.quit();
    }

});