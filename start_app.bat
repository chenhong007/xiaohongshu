@echo off
chcp 65001 >nul
echo ========================================
echo   小红书采集系统启动脚本
echo ========================================
echo.

:: 启动后端服务
echo [1/2] 启动后端服务...
cd /d "%~dp0backend"
start "XHS Backend" cmd /k "python run.py"

:: 等待后端启动
timeout /t 3 /nobreak >nul

:: 启动前端服务
echo [2/2] 启动前端服务...
cd /d "%~dp0"
start "XHS Frontend" cmd /k "npm run dev"

echo.
echo ========================================
echo   服务启动中...
echo   后端地址: http://localhost:8000
echo   前端地址: http://localhost:5173
echo ========================================
echo.
echo 按任意键关闭此窗口...
pause >nul
