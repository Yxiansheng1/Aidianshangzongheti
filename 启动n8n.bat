@echo off
chcp 65001 >nul
title n8n · 电商编排
cd /d "%~dp0"

echo ============================================
echo  n8n 编排层
echo ============================================
echo.

rem 检查工作台是否在跑（流程要调它的接口）
curl.exe --silent --fail --max-time 3 http://127.0.0.1:8899/api/status >nul 2>&1
if errorlevel 1 (
    echo [!] 本地工作台 8899 没在跑。
    echo     流程会调不到 /api/gen，请先运行 启动工作台.bat
    echo.
)

curl.exe --silent --fail --max-time 3 http://127.0.0.1:5678/rest/settings >nul 2>&1
if not errorlevel 1 (
    echo [1/1] n8n 已在运行
    start "" http://localhost:5678
    exit /b
)

echo [1/1] 正在启动 n8n...
set N8N_USER_FOLDER=D:\n8n\data
set N8N_PORT=5678
set N8N_SECURE_COOKIE=false
set N8N_DIAGNOSTICS_ENABLED=false

start "" /min cmd /c "timeout /t 12 /nobreak >nul && start http://localhost:5678"

"D:\n8n\node_modules\.bin\n8n.cmd" start

echo.
echo n8n 已退出。
pause
