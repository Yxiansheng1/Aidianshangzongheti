@echo off
chcp 65001 >nul
title AI 电商综合体 · 工作台
cd /d "%~dp0"

echo ============================================
echo  AI 电商综合体
echo ============================================
echo.

rem ---------- 工作台已经在跑？直接开浏览器 ----------
curl.exe --silent --fail --max-time 3 http://127.0.0.1:8899/api/status >nul 2>&1
if not errorlevel 1 (
    echo 工作台已在运行，直接打开浏览器。
    start "" http://127.0.0.1:8899
    timeout /t 2 /nobreak >nul
    exit /b 0
)

rem ---------- ComfyUI ----------
curl.exe --silent --fail --max-time 3 http://127.0.0.1:8188/system_stats >nul 2>&1
if not errorlevel 1 (
    echo [1/2] ComfyUI 已在运行
    goto gui
)

echo [1/2] 启动 ComfyUI（8GB 显存模式，约 20 秒）...

if not exist "D:\AI\ComfyUI_windows_portable\Start_Wan_8GB.bat" (
    echo     [!] 找不到 D:\AI\ComfyUI_windows_portable\Start_Wan_8GB.bat
    echo         跳过 ComfyUI，出图功能会不可用
    goto gui
)

start "" /min "D:\AI\ComfyUI_windows_portable\Start_Wan_8GB.bat"

set /a tries=0

:wait
set /a tries+=1
if %tries% gtr 40 goto timeout
timeout /t 2 /nobreak >nul
curl.exe --silent --fail --max-time 3 http://127.0.0.1:8188/system_stats >nul 2>&1
if errorlevel 1 goto wait
echo     ComfyUI 就绪
goto gui

:timeout
echo     [!] ComfyUI 80 秒没起来，先继续启动工作台
echo         出图和视频会不可用，可以手动双击 Start_Wan_8GB.bat 看报错

:gui
echo [2/2] 启动工作台...
echo.
echo  地址: http://127.0.0.1:8899
echo  关掉这个窗口就停止服务
echo.

python -m pipeline gui --port 8899 --open

echo.
echo ============================================
echo  工作台已退出（错误码 %errorlevel%）
echo ============================================
echo.
echo 如果上面有红字报错，把那一整段复制发给 AI。
pause
