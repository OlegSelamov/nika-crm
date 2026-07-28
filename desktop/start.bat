@echo off
title Nika Business TEST

cd /d "D:\PRO\nika_business"

set "NIKA_ENV_FILE=.env.test"

start "" /b "C:\Users\user\AppData\Local\Programs\Python\Python311\python.exe" app.py

timeout /t 4 /nobreak >nul

cd /d "D:\PRO\nika_business\desktop"
npm start