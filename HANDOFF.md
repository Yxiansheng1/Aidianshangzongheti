# HANDOFF · 交给下一个 harness

> 最后更新：2026-11-06 ｜ 基座提交：`86fddcc`
> 这份文档的目标：**新会话冷启动，读完就能干活，不用翻聊天记录。**

---

## 一、这个项目是什么

一个人用的本地工作台，两条业务线共用一套底座：

```
内容线：选题 → 取材 → 写稿 → 审核 → 配图 → 填进编辑器 → 人点发布 → 收数据
电商线：找品 → 评分 → 素材 → 上架资料包 → 分发
```

核心不是"AI 聊天框"，而是**AI 当调度员**：给一个目标，它自己拆步骤、调工具、在关键节点停下来等人批准。

---

## 二、当前真实状态（截至本次交接）

### 能跑通的（有证据）

| 能力 | 证据 | 位置 |
|---|---|---|
| harness 三档自主度 | 16 个测试 | `pipeline/harness/policy.py` + `tests/test_policy.py` |
| 工具注册与审批门禁 | 18 个测试 | `pipeline/harness/registry.py` + `tests/test_registry.py` |
| 真模型「停→批→续」 | `scripts/harness_smoke_model.py` 实跑 | `docs/hitl-实测.md` |
| 任务运行时 + 四个接口 | 13 个测试 | `pipeline/harness/runtime.py`、`pipeline/api/app.py` |
| 真模型端到端 | `scripts/e2e_task.py`：模型真抓了一个网页并报告字数 | 同上 |
| Electron 壳 + 进程管理 | 独立复跑 9+6 项全 PASS | `app/` |
| 头条两个号发稿 | 各发 1 篇，真实数据 | 见第五节链接 |

**测试总数：70 个，约 1.3 秒全绿。**

### 卡住的 / 没做的

| 事项 | 原因 | 谁能解决 |
|---|---|---|
| 百家号两个号未实名 | 平台要求身份证+人脸 | **只能用户本人** |
| 头条 `publish` 会真发 | 工具已接，但没有沙箱 | 需要"演练模式" |
| 审批状态不持久 | 用的是 `InMemorySaver` | 换成 SqliteSaver（下一轮第一件事） |
| 电商线未接入 harness | 只在老结构里 | 需要新工具 + 新 lane |
| 客户端只有状态页 | 没做审批卡片 | 接 `/api/tasks` 即可 |

---

## 三、架构（四层，改东西前先看这张图）

```
① 控制台 console   内容台 电商台 发布台 账号台 数据台        ← app/（Electron）
        ↓ 只走 HTTP
② 任务/业务线     任务运行时（跑→停→批→续）                 ← pipeline/harness/runtime.py
        ↓ 只调能力
③ 能力→工具       fetch / write / image / fill / publish     ← pipeline/tools/
        ↓ 平台差异只允许在这里
④ 平台驱动        头条 / 百家号 / sau 的 8 个平台            ← pipeline/content/headline.py 等
──────────────────────────────────────────────────────────
⑤ 底座            账号 / 稿件 / 素材 / 商品 / 数据            ← 尚未建（见第七节）
```

**两条纪律**（违反就会退回"一锅粥"）：
1. 平台差异不许漏到上层（"头条不能自动发"这种知识只写在驱动里）
2. 一个能力只留一份实现（电商改写与自媒体改写要合并，别各写一份）

---

## 四、怎么跑起来

### 环境

```
系统 Python 3.12.10        ← 跑老的工作台、老脚本
.venv\（Python 3.12）       ← 跑 harness：deepagents 0.7.32 + langchain 1.4.9 + langgraph 1.2.20
D:\social-auto-upload\.venv ← 浏览器自动化（patchright）+ sau，头条/百家号登录态在这里
```

**注意**：harness 的 `.venv` 里**没有 patchright**，也不该有。填稿/发布必须走 subprocess 调 sau 的 venv。

### 常用命令

```powershell
# 全量测试
.\.venv\Scripts\python.exe -m pytest tests -q

# 看三档审批闸门（不需要模型）
.\.venv\Scripts\python.exe scripts\harness_check.py

# 真模型验证「停→批→续」
.\.venv\Scripts\python.exe scripts\harness_smoke_model.py

# 起本地 API（客户端会用它）
.\.venv\Scripts\python.exe -m pipeline.api     # 127.0.0.1:8765，文档 /docs

# 端到端：交任务 → 轮询 → 看结果
.\.venv\Scripts\python.exe scripts\e2e_task.py

# Electron 壳
cd app; pnpm.cmd dev

# 老工作台（电商线旧界面，仍可用）
python -m pipeline gui --port 8899
```

### 模型

`config.toml` 的 `[model]`：`deepseek-v4-pro` @ `https://www.tokenav.ai/v1`（OpenAI 兼容网关）。
换模型只改这里；代码里走 `langchain_openai.ChatOpenAI`。

---

## 五、真实账号与已发布内容

| 号 | 平台 | 昵称 | 状态 |
|---|---|---|---|
| 号1 | 头条 | 老韩读报（审核中，暂显默认名） | ✅ 可发 |
| 号2 | 头条 | 档案室 | ✅ 可发 |
| 号1 | 百家号 | 掌晗昱26（默认名） | ❌ 未实名 |
| 号2 | 百家号 | 美好又冷静丶萨摩0y（默认名） | ❌ 未实名 |

已发布：

- 号1 头条《37辆豹2A8在挪威开造》 https://www.toutiao.com/article/7702508210401460746/
- 号2 头条《427座隧道、991座桥：成昆铁路怎么修出来的》 https://www.toutiao.com/article/7702514908738372122/

**内容分工（重要）**：头条写"发生了什么"（事件），百家号写"他想知道什么"（搜索问题）。
同一题材 72 小时内不要两边都发，否则两边首发资格都没了。详见 `output/账号资料/头条与百家号-内容分工.md`。

---

## 六、已经踩过的坑（别重复踩）

### harness / 框架层

1. **`checkpointer=True` 会炸**：langgraph 1.2 起根图必须给真实 saver（`InMemorySaver()`），否则 `RuntimeError`。
2. **审批恢复格式**：`Command(resume={"decisions": {0: {"type": "approve"}}})`——键是**动作序号**，不是 interrupt id。试过 `{id: ...}`、`{"type": "approve"}`、`True` 全部报错。
3. **恢复时被中断的节点会从头重跑**：副作用（发布、扣款）绝不能放在 `interrupt()` 之前。
4. **`Exception.args` 不能自定义**：我写过 `self.args = tool_args`，被基类覆盖，测试当场抓到。

### 头条 / 百家号

5. **话题不是正文打 `#`**：必须是 `tteditor-forum` 节点（候选框点选），纯文本不算。
6. **两个号必须核对 `user_id`**：靠昵称判断会翻车，同一个人扫两次码会变成同一个号。
7. **登录判断别看编辑器**：编辑器对未登录用户也渲染；要看后台首页能否进入。
8. **保存后页面不刷新**：回读要整页 `reload()`。
9. **百家号发布有滑动验证**：反自动化机制，不绕过；百家号只能是半自动（我填稿，人过验证点发布）。

### 浏览器自动化通用

10. **`position: fixed` 元素 `offsetParent` 为 `null`**：可见性判断要用 `getBoundingClientRect()`。
11. **React / 级联组件不认 JS `.click()`**：必须真实鼠标事件（Playwright `locator.click()` 或 `page.mouse.click`）。
12. **输入框可能没有 `type` 属性**：`input[type=text]` 选不到，用 `input:not([type=file])`。
13. **「确定」按钮可能带计数**：`确定 (1)`，精确匹配会失败。

### Windows / 进程

14. **Python sidecar 是孙进程**：`venv\python.exe -m x` 会再 spawn 系统 python，只杀父进程会留孤儿占端口 → `taskkill /T /F`。
15. **PowerShell 拦 `.ps1`**：`npm`/`pnpm` 要用 `npm.cmd` / `pnpm.cmd`。
16. **控制台 cp1252**：Python 输出中文要先 `sys.stdout.reconfigure(encoding="utf-8")`，否则服务启动即崩。

---

## 七、下一步（按优先级）

| # | 任务 | 为什么先做 | 大概工作量 |
|---|---|---|---|
| 1 | **SqliteSaver 替换内存 checkpoint** | 现在后端一重启，等审批的任务全丢 | 半天 |
| 2 | **把真实写稿流程接进 harness** | 现在只验证了抓取；写稿/配图/填稿还没串起来 | 1 天 |
| 3 | **Electron 审批卡片** | 接 `/api/tasks`，界面能点同意/驳回 | 1 天 |
| 4 | **底座：SQLite 实体表** | 稿件/素材/账号现在还是散文件 | 半天 |
| 5 | **电商线接入** | 复用同样的工具 + lane 模式 | 待评估 |
| 6 | 百家号实名 | 只能用户本人做 | 15 分钟（用户） |

**建议的竖切**：先只做「给号2 写一篇三线建设的稿 → 停下等审批 → 填进编辑器」，跑通这一条再扩。

---

## 八、目录地图

```
pipeline/
  harness/            ★ 智能体运行时（本项目的核心）
    policy.py         三档自主度 + 自动降档
    registry.py       工具注册表 + 审批门禁
    agent.py          装配 Deep Agents（interrupt_on / skills / memory）
    approval.py       审批解析与提交（把格式坑封死）
    runtime.py        任务运行时（跑→停→批→续）
  tools/              ★ 五个工具（L2 交付）
  api/                ★ 本地 FastAPI（8765）
  content/            内容线：抓文/改写/审核/配图/头条驱动/百家号驱动
  content/skills/     9 个平台写作规则（markdown，Deep Agents 的 Skills 直接用）
  content/modes/      3 个题材硬规则
  content/topics/     历史题库 40 题
  article.py fetch.py review.py trends.py   ← 老内容线能力，工具层在调
  writer.py analyze.py pick/ listing.py      ← 电商线（旧）
app/                  ★ Electron 壳（状态页 + 进程管理）
tests/                ★ 70 个测试
scripts/              正式工具（29 个）
scripts/probes/       历史试错脚本（21 个，只做参考，不要当正式入口）
docs/                 架构方案、HITL 实测、并发分工、老教程 01-10
coordination/         多会话协作的信箱记录（历史，新 harness 可忽略）
```

---

## 九、给新 harness 的开场白

如果要接着干，把下面这段贴进去即可：

> 读 `HANDOFF.md` 和 `docs/架构重构方案.md`。
> 项目现在处于"harness 已通、真实流程未接"的状态：`pipeline/harness/` 五个模块 + `pipeline/tools/` 五个工具 + `pipeline/api/` 四个任务接口都能跑，70 个测试全绿。
> 下一步第一件事是：把 `InMemorySaver` 换成 `SqliteSaver`，让审批状态跨进程重启。
> 纪律：平台差异只写在驱动里；一个能力只留一份实现；改完跑 `pytest tests -q`；不要碰 `config.toml`。

---

## 十、已知债务（诚实清单）

- 老工作台 `pipeline/gui/`（server.py 48KB + ui.html 80KB）与新架构并存，尚未拆台
- 电商线的 `writer.py` 与内容线的 `rewrite.py` 是同一能力的两份实现，未合并
- `pipeline/tools/publisher.py` 的 `publish` 会真发，没有沙箱/演练模式
- 审批状态在内存里，重启即丢
- 客户端只有状态页，没有审批界面、没有工具列表页
- `docs/01-10` 是电商线的旧教程，部分内容已过时（新架构看 `docs/架构重构方案.md`）
