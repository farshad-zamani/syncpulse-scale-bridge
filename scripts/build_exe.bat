@echo off
rem SyncPulse Scale Bridge - build dist\SyncPulseScaleBridge.exe
rem Copyright (C) 2026 Farshad Zamani - Cloudtart (https://cloudtart.com) - GPL-3.0-or-later
setlocal
cd /d "%~dp0\.."

if "%PYTHON%"=="" (
  where py >nul 2>&1 && (set "PYTHON=py -3") || (set "PYTHON=python")
)

if not exist .venv\Scripts\python.exe (
  echo Creating .venv ...
  %PYTHON% -m venv .venv || goto :error
)
.venv\Scripts\python.exe -m pip install --quiet --upgrade pip || goto :error
.venv\Scripts\python.exe -m pip install --quiet -r requirements-dev.txt || goto :error
.venv\Scripts\python.exe -m pytest -q || goto :error
.venv\Scripts\python.exe scripts\build.py || goto :error
echo.
echo Done: dist\SyncPulseScaleBridge.exe
exit /b 0

:error
echo.
echo Build failed.
exit /b 1
