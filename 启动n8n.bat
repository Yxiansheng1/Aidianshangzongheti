@echo off
chcp 65001 >nul
title n8n · 电商编排
cd /d "%~dp0"

echo ============================================
echo  n8n 编排层
echo ============================================
echo.

rem ---------- n8n 已经在跑？直接开浏览器 ----------
curl.exe --silent --fail --max-time 3 http://127.0.0.1:5678/rest/settings >nul 2>&1
if not errorlevel 1 (
    echo n8n 已在运行，直接打开浏览器。
    start "" http://localhost:5678
    timeout /t 2 /nobreak >nul
    exit /b 0
)

rem ---------- 提醒：流程要调工作台 ----------
curl.exe --silent --fail --max-time 3 http://127.0.0.1:8899/api/status >nul 2>&1
if errorlevel 1 (
    echo [!] 本地工作台 8899 没在跑，流程会调不到 /api/gen
    echo     请先运行 启动工作台.bat
    echo.
)

set N8N_USER_FOLDER=D:\n8n\data
set N8N_PORT=5678
set N8N_LISTEN_ADDRESS=127.0.0.1
set N8N_SECURE_COOKIE=false
set N8N_DIAGNOSTICS_ENABLED=false

echo [1/1] 启动 n8n（首次启动约 10-20 秒）...
echo.
echo  地址: http://localhost:5678
echo  关掉这个窗口就停止服务
echo.

start "" /min cmd /c "timeout /t 14 /nobreak >nul && start http://localhost:5678"

"D:\n8n\node_modules\.bin\n8n.cmd" start

echo.
echo ============================================
echo  n8n 已退出（错误码 %errorlevel%）
echo ============================================
echo.
echo 如果上面有红字报错，把那一整段复制发给 AI。
pause
