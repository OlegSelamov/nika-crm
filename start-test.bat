@echo off
title Nika Business TEST

cd /d "%~dp0"

set "NIKA_ENV_FILE=.env.test"

echo ========================================
echo NIKA BUSINESS TEST
echo ENV: %NIKA_ENV_FILE%
echo ========================================
echo.

if not exist ".env.test" (
    echo ERROR: .env.test not found
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