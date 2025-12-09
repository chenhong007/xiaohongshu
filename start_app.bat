@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ==========================================
echo       Xiaohongshu Spider & Frontend
echo ==========================================

:: 1. Skip UAC check to preserve current Conda environment
::    (User requested using current environment and no UAC popup)

:: 2. Check User Config (Cookie)
if not exist "backend\user_config.json" (
    echo [INFO] User config not found.
    echo [INFO] Attempting to fetch cookies from Chrome to auto-login...
    echo [INFO] Please ensure Chrome is open and logged in to Xiaohongshu.
    cd backend
    python main.py --browser_cookie Chrome --update_settings
    cd ..
) else (
    echo [INFO] User config found.
)

echo.
echo [INFO] Launching services using current environment...

:: 3. Start Backend and Frontend
:: Using 'start' creates a new window that inherits the current environment (including Conda)
echo [INFO] Starting Backend Server...
start "XHS Backend" cmd /k "cd backend && python server.py"

echo [INFO] Starting Frontend...
start "XHS Frontend" cmd /k "npm run dev"

echo.
echo ==========================================
echo    System Started Successfully!
echo.
echo    Frontend: http://localhost:5173
echo    Backend:  http://localhost:8000
echo.
echo    You can close this launcher window.
echo ==========================================
pause
