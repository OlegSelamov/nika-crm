@echo off

cd /d %~dp0

start "" pythonw app.py

:waitloop

curl http://127.0.0.1:5000 >nul 2>&1

if errorlevel 1 (
    timeout /t 1 >nul
    goto waitloop
)

start chrome --app=http://127.0.0.1:5000