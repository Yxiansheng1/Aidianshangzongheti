/**
 * 不开窗口验证进程管理：拉起后端 → 探活 → 手动杀掉 → 探活失败 → 关停清理。
 *
 * 用法：node scripts/verify-process.mjs
 * 退出码 0 = 全过，1 = 有环节没过。
 */

import { createRequire } from "node:module";
import { execSync } from "node:child_process";

const require = createRequire(import.meta.url);
const { BackendService, probeHealth, IS_WINDOWS } = require("../electron/backend-service.js");

const HOST = "127.0.0.1";
const PORT = 8765;

let failed = 0;
function check(name, ok, detail = "") {
  console.log(`${ok ? "[PASS]" : "[FAIL]"} ${name}${detail ? " — " + detail : ""}`);
  if (!ok) failed++;
}

function listApiProcesses() {
  if (!IS_WINDOWS) return "";
  try {
    // wmic 在新版 Windows 上已被移除，用 PowerShell 的 CIM 查询。
    return execSync(
      'powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \\"name=\'python.exe\'\\" | Select-Object -ExpandProperty CommandLine"',
      { encoding: "utf8" },
    );
  } catch {
    return "";
  }
}

async function main() {
  console.log(`== 进程管理验证 == 平台=${process.platform} 端口=${PORT}\n`);

  const backend = new BackendService({ host: HOST, port: PORT });
  backend.log = (m) => console.log("  " + m);
  backend.onExit = (info) => console.log("  [exit]", JSON.stringify(info));

  console.log("-- 1. 拉起后端 --");
  const pid = backend.start();
  check("spawn 拿到 pid", Boolean(pid), `pid=${pid}`);

  const ready = await backend.waitReady(30000);
  check("后端起来并响应 /api/health", ready.ok, JSON.stringify(ready.body || ready.error));

  console.log("\n-- 2. 手动杀掉后端（模拟后端崩溃/被外部杀掉）--");
  const killResult = IS_WINDOWS
    ? execSync(`taskkill /PID ${pid} /T /F`, { encoding: "utf8" })
    : "";
  console.log("  " + String(killResult).trim().split(/\r?\n/).join(" | "));

  await new Promise((r) => setTimeout(r, 1500));
  const afterKill = await probeHealth({ host: HOST, port: PORT });
  check("杀掉后探活失败（= 界面会显示后端断开）", !afterKill.ok, afterKill.error || "");

  const portBusy = await probeHealth({ host: HOST, port: PORT });
  check("端口已释放（无孤儿进程占着）", !portBusy.ok);

  console.log("\n-- 3. 重新拉起 --");
  const pid2 = backend.start();
  const ready2 = await backend.waitReady(30000);
  check("重启后端成功", ready2.ok, `pid=${pid2}`);

  console.log("\n-- 4. 退出客户端时回收子进程 --");
  const stopResult = await backend.stop();
  check("stop 返回成功", stopResult.ok, JSON.stringify(stopResult));
  check("stop 后端口释放", stopResult.portReleased === true);

  const final = await probeHealth({ host: HOST, port: PORT });
  check("最终探活仍失败（进程确实没了）", !final.ok, final.error || "");

  console.log("\n-- 5. 残留进程检查 --");
  const remaining = listApiProcesses();
  const leaked = remaining
    .split(/\r?\n/)
    .filter((l) => l.includes("pipeline.api") && l.trim());
  check("没有残留的 pipeline.api 进程", leaked.length === 0, leaked.join(" | "));

  console.log(`\n== 结果：${failed === 0 ? "全部通过" : failed + " 项未通过"} ==`);
  process.exit(failed === 0 ? 0 : 1);
}

main().catch((err) => {
  console.error("验证脚本炸了：", err);
  process.exit(1);
});
