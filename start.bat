@echo off
setlocal enabledelayedexpansion

:: DMXX Startup Script for Windows

set "SCRIPT_DIR=%~dp0"
set "CONFIG_FILE=%SCRIPT_DIR%config.json"

:: Default values
set "PORT=8000"
set "HOST=0.0.0.0"

:: Read from config.json if it exists
if exist "%CONFIG_FILE%" (
    for /f "delims=" %%i in ('python -c "import json; print(json.load(open(r'%CONFIG_FILE%')).get('port', 8000))" 2^>nul') do set "PORT=%%i"
    for /f "delims=" %%i in ('python -c "import json; print(json.load(open(r'%CONFIG_FILE%')).get('host', '0.0.0.0'))" 2^>nul') do set "HOST=%%i"
)

:: Override with environment variables if set
if defined DMXX_PORT set "PORT=%DMXX_PORT%"
if defined DMXX_HOST set "HOST=%DMXX_HOST%"

cd /d "%SCRIPT_DIR%"

:: Kill any existing process on the same port
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING" 2^>nul') do (
    echo Stopping existing process on port %PORT%...
    taskkill /PID %%a /F >nul 2>&1
    echo Waiting 5 seconds for clean shutdown...
    timeout /t 5 /nobreak >nul
)

:: Build frontend if dist doesn't exist
if not exist "frontend\dist" (
    echo Building frontend...
    pushd frontend
    call npm run build
    popd
)

echo Starting DMXX on http://%HOST%:%PORT%

:: Try to find uvx
where uvx >nul 2>&1
if %errorlevel% equ 0 (
    uvx --with-requirements backend/requirements.txt uvicorn backend.main:app --host %HOST% --port %PORT%
) else (
    echo Error: uvx not found. Please install uv first.
    echo Install with: pip install uv
    pause
    exit /b 1
)
