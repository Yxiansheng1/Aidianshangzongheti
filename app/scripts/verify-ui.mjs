/**
 * UI 验证的外层：跑真 Electron 主进程 → 读它的报告 → 查残留进程。
 *
 * 用法：node scripts/verify-ui.mjs
 * 退出码 0 = 全过。
 *
 * 验证剧本本身在 electron/main.js 的 AID_VERIFY_UI 模式里，
 * 这样跑的是真实主进程代码，不是另写一份模拟。
 */

import { createRequire } from "node:module";
import { execSync, spawnSync } from "node:child_process";
import { readFileSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const { probeHealth, IS_WINDOWS } = require("../electron/backend-service.js");

const HOST = "127.0.0.1";
const PORT = 8765;
const APP_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPORT = path.join(APP_DIR, ".verify", "report.json");

let failed = 0;
function check(name, ok, detail = "") {
  console.log(`${ok ? "[PASS]" : "[FAIL]"} ${name}${detail ? " — " + detail : ""}`);
  if (!ok) failed++;
}

function listApiProcesses() {
  if (!IS_WINDOWS) return [];
  try {
    const out = execSync(
      'powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \\"name=\'python.exe\'\\" | Select-Object -ExpandProperty CommandLine"',
      { encoding: "utf8" },
    );
    return out.split(/\r?\n/).filter((l) => l.includes("pipeline.api"));
  } catch {
    return [];
  }
}

console.log("== UI 验证（跑真实 Electron 主进程）==\n");

const electron = path.join(APP_DIR, "node_modules", "electron", "dist", "electron.exe");
if (!existsSync(electron)) {
  console.error("electron 没装好，先跑 pnpm.cmd install");
  process.exit(1);
}

const run = spawnSync(electron, [path.join(APP_DIR, "electron", "main.js")], {
  cwd: APP_DIR,
  env: { ...process.env, AID_VERIFY_UI: "1", AID_API_PORT: String(PORT) },
  encoding: "utf8",
  timeout: 120000,
});

const output = `${run.stdout || ""}\n${run.stderr || ""}`;
for (const line of output.split(/\r?\n/)) {
  if (/^\[(PASS|FAIL)\]/.test(line) || line.startsWith("[status]")) console.log("  " + line);
}

console.log("\n-- 读主进程报告 --");
let report = null;
if (existsSync(REPORT)) {
  report = JSON.parse(readFileSync(REPORT, "utf8"));
  for (const step of report.steps) {
    check(step.name, step.ok, step.detail);
  }
} else {
  check("主进程报告存在", false, REPORT);
}

console.log("\n-- 残留检查 --");
const leaked = listApiProcesses();
check("退出客户端后没有残留 pipeline.api 进程", leaked.length === 0, leaked.join(" | "));

const final = await probeHealth({ host: HOST, port: PORT });
check("端口 8765 已释放", !final.ok, final.error || "");

console.log(`\n== 结果：${failed === 0 ? "全部通过" : failed + " 项未通过"} ==`);
process.exit(failed === 0 ? 0 : 1);
