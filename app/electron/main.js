"use strict";

/**
 * Electron 主进程。
 *
 * 职责只有两件：
 *   1. 窗口里显示后端状态（连上了 / 断了 / 重连中）；
 *   2. 自己退出时，把后端子进程收干净。
 *
 * 界面这轮只放一个状态页，不做业务。
 *
 * 另外支持一个验证模式：AID_VERIFY_UI=1 时，主进程自己跑一遍
 * 「连上 → 杀掉后端 → 断开 → 退出回收」的剧本，并把截图与报告写到 app/.verify/。
 * 这样验证跑的是真实的主进程代码，不是另写一份模拟。
 */

const path = require("node:path");
const fs = require("node:fs");
const { app, BrowserWindow, ipcMain } = require("electron");

const { BackendService, DEFAULT_HOST, DEFAULT_PORT } = require("./backend-service");

const HOST = process.env.AID_API_HOST || DEFAULT_HOST;
const PORT = Number(process.env.AID_API_PORT || DEFAULT_PORT);
const VERIFY_DIR = path.join(__dirname, "..", ".verify");

let mainWindow = null;
let backend = null;
/** 验证模式下，报告是否全绿；决定退出码。 */
let verifyPassed = null;
/** 上一次探活的结果，渲染进程靠它画状态。 */
let lastStatus = { state: "starting", detail: "正在启动后端…", at: new Date().toISOString() };

function pushStatus(state, detail) {
  lastStatus = { state, detail, at: new Date().toISOString() };
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("backend-status", lastStatus);
  }
  console.log(`[status] ${state} ${detail}`);
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 720,
    height: 480,
    title: "AI 电商综合体 · 本地客户端",
    backgroundColor: "#11151c",
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.loadFile(path.join(__dirname, "index.html"));

  // 窗口画完再显示，否则会闪一下白屏；顺便 focus，capturePage 才拍得到内容。
  mainWindow.once("ready-to-show", () => {
    mainWindow.show();
    mainWindow.focus();
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

/**
 * 后端意外退出（被手动杀掉）时，窗口要立刻显示"后端断开"。
 * 杀进程是本轮要验证的关键行为，这条回调就是它的落点。
 */
function handleBackendExit(info) {
  if (info && info.stopping) {
    pushStatus("stopped", "后端已关闭");
    return;
  }
  pushStatus("disconnected", "后端断开（进程已退出）");
}

async function startBackend() {
  backend = new BackendService({
    host: HOST,
    port: PORT,
    log: (msg) => console.log(`[backend] ${msg}`),
  });
  backend.onExit = handleBackendExit;

  pushStatus("starting", "正在启动后端…");
  backend.start();

  const ready = await backend.waitReady(30000);
  if (ready.ok) {
    const v = ready.body && ready.body.version ? ` v${ready.body.version}` : "";
    pushStatus("connected", `后端已连接 ${backend.baseUrl}${v}`);
  } else {
    pushStatus("disconnected", `后端启动失败：${ready.error || "未响应"}`);
  }
  return ready;
}

/** 周期性探活：后端被手动杀掉后，窗口会自动切到"后端断开"。 */
function startHealthWatch() {
  setInterval(async () => {
    if (!backend) return;
    const res = await backend.probe();
    if (!res.ok) {
      pushStatus("disconnected", "后端断开（探活失败）");
    } else if (lastStatus.state !== "connected") {
      pushStatus("connected", `后端已连接 ${backend.baseUrl}`);
    }
  }, 3000);
}

// ---------------------------------------------------------------- 验证模式

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

/** 读窗口 DOM 上的状态文字。 */
async function readWindowState() {
  if (!mainWindow || mainWindow.isDestroyed()) return null;
  return mainWindow.webContents.executeJavaScript(
    `(() => ({
       state: (document.getElementById('dot') || {}).className || '',
       label: (document.getElementById('label') || {}).textContent || '',
       detail: (document.getElementById('detail') || {}).textContent || '',
     }))()`,
  );
}

async function shot(name) {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  await sleep(600);
  const img = await mainWindow.webContents.capturePage();
  fs.mkdirSync(VERIFY_DIR, { recursive: true });
  fs.writeFileSync(path.join(VERIFY_DIR, name), img.toPNG());
  console.log(`[shot] ${name} ${img.getSize().width}x${img.getSize().height}`);
}

/** 杀后端进程树（模拟后端被外部干掉）。 */
function killBackendTree() {
  const { spawnSync } = require("node:child_process");
  if (!backend || !backend.proc) return { ok: false, reason: "后端没在跑" };
  const pid = backend.proc.pid;
  const r = spawnSync("taskkill", ["/PID", String(pid), "/T", "/F"], { encoding: "utf8" });
  return { ok: r.status === 0, pid, stdout: (r.stdout || "").trim(), stderr: (r.stderr || "").trim() };
}

/**
 * 跑一遍验证剧本，结果写到 .verify/report.json。
 * 外层脚本（scripts/verify-ui.mjs）拿这份报告 + 自己的残留检查来判绿。
 */
async function runVerification() {
  const report = { steps: [], ok: true };
  const add = (name, ok, detail) => {
    report.steps.push({ name, ok, detail });
    if (!ok) report.ok = false;
    console.log(`${ok ? "[PASS]" : "[FAIL]"} ${name}${detail ? " — " + detail : ""}`);
  };

  try {
    const s1 = await readWindowState();
    add("窗口显示后端已连接", !!s1 && (s1.label.includes("已连接") || s1.state.includes("connected")), JSON.stringify(s1));
    await shot("01-connected.png");

    const killed = killBackendTree();
    add("手动杀掉后端进程树", killed.ok, killed.stdout || killed.stderr || JSON.stringify(killed));

    await sleep(6000);
    const s2 = await readWindowState();
    add("窗口提示后端断开", !!s2 && (s2.label.includes("断开") || s2.state.includes("disconnected")), JSON.stringify(s2));
    await shot("02-disconnected.png");

    // 重新拉起一个，留给退出清理用
    backend.proc = null;
    const restarted = await startBackend();
    add("重启后端成功（为退出回收做准备）", restarted.ok, JSON.stringify(restarted.body || restarted.error));
    await sleep(1200);
    await shot("03-restarted.png");

    report.backendPid = backend.proc ? backend.proc.pid : null;
  } catch (err) {
    add("验证剧本执行", false, String(err && err.stack ? err.stack : err));
  }

  return report;
}

// ---------------------------------------------------------------- 生命周期

ipcMain.handle("backend:get-status", () => lastStatus);
ipcMain.handle("backend:probe", async () => {
  const { probeHealth } = require("./backend-service");
  const res = await probeHealth({ host: HOST, port: PORT });
  pushStatus(res.ok ? "connected" : "disconnected", res.ok ? "后端已连接" : "后端断开");
  return res;
});

app.whenReady().then(async () => {
  createWindow();
  await startBackend();
  startHealthWatch();

  if (process.env.AID_VERIFY_UI === "1") {
    const report = await runVerification();
    fs.mkdirSync(VERIFY_DIR, { recursive: true });
    fs.writeFileSync(path.join(VERIFY_DIR, "report.json"), JSON.stringify(report, null, 2));
    // 用 app.quit() 而不是 app.exit()：后者会绕过 before-quit，
    // 那样就验不到"退出时回收子进程"这条路径了。
    verifyPassed = report.ok;
    app.quit();
    return;
  }

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  app.quit();
});

/**
 * 退出清理。
 *
 * 顺序很重要：先杀后端，再让 Electron 自己退。
 * 'before-quit' 里 async 不保证被 await，所以这里用显式的 app.exit 收尾，
 * 另配一个同步的 taskkill 兜底。
 */
let quitting = false;
app.on("before-quit", (event) => {
  if (quitting) return;
  quitting = true;
  event.preventDefault();

  (async () => {
    try {
      const result = await backend.stop();
      console.log(`[backend] 退出清理完成：${JSON.stringify(result)}`);
      if (verifyPassed !== null && !result.portReleased) verifyPassed = false;
    } catch (err) {
      console.error("[backend] 退出清理出错：", err);
      if (verifyPassed !== null) verifyPassed = false;
    }
    app.exit(verifyPassed === null ? 0 : verifyPassed ? 0 : 1);
  })();
});

/** 兜底：进程被强杀时，至少不留孤儿（Windows 上用 taskkill 同步杀树）。 */
process.on("exit", () => {
  if (backend && backend.proc && !backend.exited) {
    try {
      require("node:child_process").spawnSync("taskkill", [
        "/PID",
        String(backend.proc.pid),
        "/T",
        "/F",
      ]);
    } catch {
      /* 已经没了就算了 */
    }
  }
});
