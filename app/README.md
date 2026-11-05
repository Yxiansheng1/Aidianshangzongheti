# app/ — 本地客户端壳

Electron 主进程负责两件事：拉起 `pipeline.api` 后端、退出时把后端子进程收干净。
界面这轮只有一个后端状态页。

## 跑

```powershell
cd app
pnpm.cmd install
pnpm.cmd dev
```

窗口里会显示后端地址与版本；后端连不上时显示"后端断开"。

## 验证

```powershell
node scripts/verify-process.mjs   # 不开窗口：拉起 → 探活 → 杀掉 → 重启 → 回收
node scripts/verify-ui.mjs        # 开真窗口：截图存 app/.verify/，再验退出回收
```

## 两个必须知道的坑

1. **Windows 上要按进程树杀。** `.venv\Scripts\python.exe -m pipeline.api` 会再 spawn 一个
   系统 python，真正监听端口的是那个孙进程。只杀父进程会留下孤儿占住 8765。
   所以关停一律 `taskkill /PID <pid> /T /F`。

2. **Electron 被强杀时靠后端自己收尸。** Windows 不会连带杀子进程。
   主进程给后端设了 `AID_API_WATCHDOG=1`，后端每 2 秒检查一次父进程，
   父进程没了就 `os._exit(0)`，避免孤儿进程霸端口。

## 目录

```
electron/main.js             主进程：窗口、状态推送、退出清理
electron/backend-service.js  进程管理（不依赖 electron，可单测）
electron/preload.js          contextBridge 白名单
electron/index.html          状态页
scripts/verify-process.mjs   无窗口的进程管理验证
scripts/verify-ui.mjs        真窗口的 UI 验证
```
