"use strict";

/**
 * åŽç«¯è¿›ç¨‹ç®¡ç†ï¼šæ‹‰èµ· pipeline.apiã€æŽ¢æ´»ã€å…³åœã€‚
 *
 * è¿™ä¸ªæ–‡ä»¶ä¸ require electronï¼Œçº¯ç²¹æ˜¯ Node çš„æ´»ã€‚ç†ç”±æœ‰ä¸¤ä¸ªï¼š
 *   1. èƒ½è¢« scripts/verify-process.mjs ç›´æŽ¥æ‹¿æ¥è·‘ï¼Œä¸å¼€çª—å£ä¹Ÿèƒ½éªŒè¯è¿›ç¨‹ç®¡ç†ï¼›
 *   2. ä¸»è¿›ç¨‹é‡Œé€»è¾‘è¶Šå°‘è¶Šä¸å®¹æ˜“å‡ºé”™ï¼Œè¿›ç¨‹ç”Ÿå‘½å‘¨æœŸæ˜¯å…¨é¡¹ç›®æœ€å®¹æ˜“å‡ºé˜´é—´ bug çš„åœ°æ–¹ã€‚
 *
 * Windows ä¸Šæœ‰ä¸ªå‘å¿…é¡»åœ¨è¿™å±‚è§£å†³ï¼š
 *   .venv\Scripts\python.exe -m pipeline.api ä¼šå† spawn ä¸€ä¸ªç³»ç»Ÿ pythonï¼Œ
 *   çœŸæ­£ listen ç«¯å£çš„æ˜¯é‚£ä¸ªå­™è¿›ç¨‹ã€‚åª kill çˆ¶è¿›ç¨‹ä¼šç•™ä¸‹å­¤å„¿ç«¯å£ï¼Œ
 *   æ‰€ä»¥å…³åœä¸€å¾‹æŒ‰è¿›ç¨‹æ ‘æ€ï¼ˆtaskkill /Tï¼‰ã€‚
 */

const path = require("node:path");
const http = require("node:http");
const { spawn, spawnSync } = require("node:child_process");
const fs = require("node:fs");

const IS_WINDOWS = process.platform === "win32";

const DEFAULT_HOST = "127.0.0.1";
const DEFAULT_PORT = 8765;

/** ä»“åº“æ ¹ç›®å½•ï¼šapp/ çš„ä¸Šä¸Šçº§ã€‚ */
const REPO_ROOT = path.resolve(__dirname, "..", "..");

/** ä¼˜å…ˆç”¨é¡¹ç›® venvï¼Œå…¶æ¬¡æ‰¾ PATH ä¸Šçš„ pythonã€‚ */
function resolvePython() {
  const venvPython = path.join(
    REPO_ROOT,
    ".venv",
    "Scripts",
    IS_WINDOWS ? "python.exe" : "bin/python",
  );
  if (fs.existsSync(venvPython)) return venvPython;
  return IS_WINDOWS ? "python" : "python3";
}

/**
 * æŽ¢æ´»ä¸€æ¬¡ã€‚ç”¨è£¸ http è€Œä¸æ˜¯ fetch/axiosï¼š
 * ä¸å¼•ä¾èµ–ï¼Œä¹Ÿé¿å¼€ Node ç‰ˆæœ¬é—´ fetch è¡Œä¸ºçš„å·®å¼‚ã€‚
 */
function probeHealth({ host = DEFAULT_HOST, port = DEFAULT_PORT, timeoutMs = 2000 } = {}) {
  return new Promise((resolve) => {
    const req = http.get(
      { host, port, path: "/api/health", timeout: timeoutMs },
      (res) => {
        const chunks = [];
        res.on("data", (c) => chunks.push(c));
        res.on("end", () => {
          const raw = Buffer.concat(chunks).toString("utf8");
          try {
            resolve({ ok: res.statusCode === 200, statusCode: res.statusCode, body: JSON.parse(raw) });
          } catch {
            resolve({ ok: false, statusCode: res.statusCode, body: null, raw });
          }
        });
      },
    );
    req.on("timeout", () => {
      req.destroy();
      resolve({ ok: false, statusCode: 0, body: null, error: "timeout" });
    });
    req.on("error", (err) => {
      resolve({ ok: false, statusCode: 0, body: null, error: err.message });
    });
  });
}

/** æŒ‰è¿›ç¨‹æ ‘æ€è¿›ç¨‹ã€‚Windows ç”¨ taskkill /Tï¼Œç±» Unix æ€æ•´ä¸ªè¿›ç¨‹ç»„ã€‚ */
function killTree(pid) {
  if (!pid) return { ok: false, reason: "no pid" };
  if (IS_WINDOWS) {
    const r = spawnSync("taskkill", ["/PID", String(pid), "/T", "/F"], { encoding: "utf8" });
    return {
      ok: r.status === 0,
      command: "taskkill /T /F",
      stdout: (r.stdout || "").trim(),
      stderr: (r.stderr || "").trim(),
    };
  }
  try {
    process.kill(-pid, "SIGTERM");
    return { ok: true, command: "kill(-pid)" };
  } catch {
    try {
      process.kill(pid, "SIGTERM");
      return { ok: true, command: "kill(pid)" };
    } catch (err) {
      return { ok: false, reason: err.message };
    }
  }
}

class BackendService {
  constructor(options = {}) {
    this.host = options.host || DEFAULT_HOST;
    this.port = options.port || DEFAULT_PORT;
    this.python = options.python || resolvePython();
    this.cwd = options.cwd || REPO_ROOT;
    this.log = options.log || (() => {});
    this.proc = null;
    this.stopping = false;
    this.exited = false;
  }

  get baseUrl() {
    return `http://${this.host}:${this.port}`;
  }

  /** spawn åŽç«¯ã€‚è¿”å›žå­è¿›ç¨‹ pidã€‚ */
  start() {
    if (this.proc && !this.exited) return this.proc.pid;
    this.stopping = false;
    this.exited = false;

    const args = ["-m", "pipeline.api", "--host", this.host, "--port", String(this.port)];
    this.log(`spawn python ${this.python} ${args.join(" ")} (cwd=${this.cwd})`);

    const child = spawn(this.python, args, {
      cwd: this.cwd,
      // Windows ä¸Š python è‡ªå·±ä¼šå†å¼€ä¸€ä¸ªå­™è¿›ç¨‹ï¼›detached è®©å­™è¿›ç¨‹è·ŸéšåŒä¸€ç»„ï¼Œ
      // å…³åœæ—¶æ‰èƒ½æŒ‰ç»„æ”¶å¹²å‡€ã€‚
      detached: !IS_WINDOWS,
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
      env: {
        ...process.env,
        PYTHONIOENCODING: "utf-8",
        PYTHONUNBUFFERED: "1",
        // è®©åŽç«¯è‡ªå·±ç›¯ç€çˆ¶è¿›ç¨‹ï¼šElectron è¢«å¼ºæ€æ—¶ python ä¼šè‡ªæ€ï¼Œä¸ç•™å­¤å„¿å ç«¯å£ã€‚
        AID_API_WATCHDOG: "1",
      },
    });

    this.proc = child;
    const relay = (stream, tag) => {
      stream.setEncoding("utf8");
      stream.on("data", (chunk) => {
        for (const line of chunk.split(/\r?\n/)) {
          if (line.trim()) this.log(`[python:${tag}] ${line}`);
        }
      });
    };
    relay(child.stdout, "out");
    relay(child.stderr, "err");

    child.on("exit", (code, signal) => {
      this.exited = true;
      this.log(`python é€€å‡º code=${code} signal=${signal}`);
      if (this.onExit) this.onExit({ code, signal, stopping: this.stopping });
    });
    child.on("error", (err) => {
      this.exited = true;
      this.log(`python å¯åŠ¨å¤±è´¥ï¼š${err.message}`);
      if (this.onExit) this.onExit({ code: null, signal: null, error: err.message, stopping: this.stopping });
    });

    return child.pid;
  }

  /** æŽ¢æ´»ä¸€æ¬¡ï¼ˆå¸¦å½“å‰ host/portï¼‰ã€‚ */
  async probe(timeoutMs = 2000) {
    return probeHealth({ host: this.host, port: this.port, timeoutMs });
  }

  /** ç­‰åŽç«¯èµ·æ¥ï¼Œæœ€å¤šç­‰ timeoutMsã€‚ */
  async waitReady(timeoutMs = 30000) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const res = await probeHealth({ host: this.host, port: this.port });
      if (res.ok) return res;
      await new Promise((r) => setTimeout(r, 400));
    }
    return { ok: false, statusCode: 0, body: null, error: "å¯åŠ¨è¶…æ—¶" };
  }

  /** å…³åœåŽç«¯ï¼šå…ˆæŒ‰æ ‘æ€ï¼Œå†ç¡®è®¤ç«¯å£çœŸçš„ç©ºäº†ã€‚ */
  async stop() {
    this.stopping = true;
    if (!this.proc) return { ok: true, reason: "æœ¬æ¥å°±æ²¡èµ·" };
    const pid = this.proc.pid;
    const result = killTree(pid);
    this.log(`å…³åœåŽç«¯ pid=${pid}ï¼š${JSON.stringify(result)}`);

    const deadline = Date.now() + 8000;
    while (Date.now() < deadline) {
      const res = await probeHealth({ host: this.host, port: this.port, timeoutMs: 800 });
      if (!res.ok) break;
      await new Promise((r) => setTimeout(r, 300));
    }
    const still = await probeHealth({ host: this.host, port: this.port, timeoutMs: 800 });
    this.proc = null;
    return { ...result, portReleased: !still.ok };
  }
}

module.exports = {
  BackendService,
  IS_WINDOWS,
  DEFAULT_HOST,
  DEFAULT_PORT,
  REPO_ROOT,
  resolvePython,
  probeHealth,
  killTree,
};

