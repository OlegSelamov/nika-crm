@echo off
set NIKA_ENV_FILE=.env.local
venv\Scripts\python.exe app.py
pause@echo off
title Nika Business LOCAL

cd /d "%~dp0"

set "NIKA_ENV_FILE=.env.local"

echo ========================================
echo NIKA BUSINESS LOCAL
echo ENV: %NIKA_ENV_FILE%
echo ========================================
echo.

if not exist ".env.local" (
    echo ERROR: .env.local not found
    pause
    exit /b 1
)

if not exist "app.py" (
    echo ERROR: app.py not found
    pause
    exit /b 1
)

"C:\Users\user\AppData\Local\Programs\Python\Python311\python.exe" app.py

pause