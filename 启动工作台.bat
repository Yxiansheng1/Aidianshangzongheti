@echo off
chcp 65001 >nul
title AI 电商综合体 · 工作台
cd /d "%~dp0"

echo ============================================
echo  AI 电商综合体
echo ============================================
echo.

curl.exe --silent --fail --max-time 3 http://127.0.0.1:8188/system_stats >nul 2>&1
if not errorlevel 1 (
    echo [1/2] ComfyUI 已在运行
    goto gui
)

echo [1/2] 正在启动 ComfyUI（8GB 显存模式，约 20 秒）...

if not exist "D:\AI\ComfyUI_windows_portable\Start_Wan_8GB.bat" (
    echo       [!] 找不到 D:\AI\ComfyUI_windows_portable\Start_Wan_8GB.bat
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
echo       ComfyUI 就绪
goto gui

:timeout
echo       [!] ComfyUI 启动超时（80 秒）
echo           工作台仍会启动，但出图/出视频不可用。
echo           手动双击 D:\AI\ComfyUI_windows_portable\Start_Wan_8GB.bat 看具体报错。

:gui
echo [2/2] 正在启动工作台...
python -m pipeline gui --port 8899 --open
echo.
echo 工作台已退出。
pause
