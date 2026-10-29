# AI 电商综合体

从「一个商品」到「多平台可发布内容」的本地流水线。

**定位：从找到一个品，到发出第一批内容，30 分钟。**

---

## 现状

当前是**第 0 步：骨架**。核心的生成与发布能力全部复用成熟开源项目，本仓库只负责中间那层胶水。

| 层 | 用什么 | 许可证 | 状态 |
|---|---|---|---|
| **本地生成** | **ComfyUI + Qwen-Image-Edit 2511** | 开源模型 | **✅ 已跑通** |
| 内容生成（批量） | [MxPage](https://github.com/ziguishian/MxPage) | MIT | 可选 |
| 模型网关 | [one-api](https://github.com/songquanpeng/one-api) | MIT | 第二阶段（可选） |
| 多平台发布 | [social-auto-upload](https://github.com/dreammis/social-auto-upload) | MIT | 待安装 |
| 选品数据 | 暂不做 | — | 后续 |
| **胶水层** | **本仓库** | 私有 | 开发中 |

### 实测数据（RTX 5060 Laptop 8GB / 63GB 内存）

| 项 | 结果 |
|---|---|
| 模型 | `qwen-image-edit-2511-Q8_0.gguf`（20.27 GB） |
| 启动 ComfyUI | 22 秒（`--lowvram`） |
| 单张 1024×1024 / 20 步 | **约 462 秒（7.7 分钟）** |
| 费用 | 0 元 |
| 商品保真 | 形状、瓶盖、标签完整保留 |


## 拼装关系

```
⓪ 热点   trends   每天抓一次热搜，筛出能蹭的（免费，自动过滤负面）
        ↓
① 分析   analyze  商品 → 分析 + 生图/视频提示词 + 小红书文案（需文本模型）
        ↓
② 选品   pick     候选池打分排序（数据你录入，模块只做判断）
        ↓
③ 出图   gen      ComfyUI + Qwen-Image-Edit   0 元，约 8 分钟/张
        ↓
④ 出视频 vid      ComfyUI + Wan2.2 I2V        0 元，很慢
        ↓
⑤ 整理   输出目录（每个商品一个文件夹）
        ↓
⑥ 清单   ingest   读目录 → manifest.json
        ↓
⑦ 发布   publish  调 social-auto-upload → 小红书 / 知乎 / 抖音 / 快手 / B站 / 视频号…
        ↓
⑧ 上架   package  生成淘宝/拼多多上架资料包（不是一键上货，见 docs/06）
```

**设计原则：模型的、平台的，全都藏在适配层后面。** 换本地/云端、换平台，主流程不动。

## 快速开始

**双击 `启动工作台.bat`** —— 会自动拉起 ComfyUI，然后打开浏览器界面：

```
http://127.0.0.1:8899
```

界面四个页签：**出图 / 视频 / 选品 / 发布**，选中图、写提示词、点按钮就行，不用记命令。

命令行方式（等价）：

```powershell
cd D:\AIdianshangzongheti
python -m pipeline gui --open
```

## 命令行

```powershell
python -m pipeline check
```

完整流程：

```powershell
# 0. 启动 ComfyUI（8GB 显存用这个）
D:\AI\ComfyUI_windows_portable\Start_Wan_8GB.bat

# 0. 热点：今天有什么能蹭的
python -m pipeline trends
python -m pipeline trends --top 5 --save

# 1. 分析：商品 → 卖点/风险/定价 + 生图与视频提示词（需文本模型 key）
python -m pipeline analyze --name "渐变杯装蜡烛" `
    --desc "手作大豆蜡，燃烧约25小时，渐变玻璃杯身" `
    --extra "1688 代发 32 元，三家现货"

# 2. 选品：生成候选池 → 填 → 排序
python -m pipeline pick init
python -m pipeline pick rank --top 2

# 3. 出图：商品原图 → 场景主图
python -m pipeline gen --image "商品原图.png" `
    --prompt "放在浅色木纹桌面，清晨侧光，浅景深，商品保持原样"

# 4. 出视频：主图 → 短视频
python -m pipeline vid --image "商品原图-场景.png" `
    --prompt "镜头缓慢推进，光影缓慢变化"

# 5. 扫目录，生成发布清单
python -m pipeline ingest --dir "D:\MxPage\output"

# 6. 发布（默认只打印，不执行）
python -m pipeline publish --platform xiaohongshu --kind note
python -m pipeline publish --platform zhihu --kind note
python -m pipeline publish --platform xiaohongshu --kind note --execute

# 7. 上架资料包（淘宝/拼多多上架前准备，不是一键上货）
python -m pipeline package
```

## 能力边界

| | 能自动 | 不能自动 |
|---|---|---|
| 出图 / 出视频 | ✅ 全自动，本地免费 | — |
| 发内容（小红书/知乎/抖音…） | ✅ 命令级自动 | 首屏登录要人，有封号风险 |
| 上货 | ⚠️ 资料准备全自动 | 录入千牛后台要人 |

平台支持矩阵、知乎长文的特殊处理、为什么"一键上货"做不了 —— 见 `docs/06-平台与上货.md`。

## 编排层（可选）

流程不在 Python 里，在 n8n 画布上：

```powershell
# 顺序：ComfyUI → 工作台 → n8n
启动工作台.bat
启动n8n.bat          # http://localhost:5678
```

- 工作流：`workflows/ecom-gen-video.json`（进仓库，可 diff、可回滚）
- 能力清单：`http://127.0.0.1:8899/api/tools`
- 账号与细节：`docs/08-编排-n8n.md`

**真正决定"可复用"的是 `/api/*` 这套契约，不是编排工具。** 换掉 n8n，能力层一行不用改。

⚠️ n8n 是 Sustainable Use License（不是 MIT）：自己用、拿它给客户做服务都可以，**但不能把 n8n 本身当产品卖**。要卖产品，底座换 MIT 的（OpenClaw / Hermes Agent）。

## 目录

```
docs/       安装清单、API Key 说明、验证记录
pipeline/   胶水层代码（仅标准库，无需安装依赖）
  model/    模型接口适配层
  ingest/   MxPage 产物解析
  publish/  发布工具适配层
samples/    脱敏的样例输入
```

## 不做的事

- 不抓取平台数据（合规风险）
- 不做自动登录、不绕过风控
- 不自动把所有内容发到所有号（封号风险）

## 风险须知

自动发布通过模拟浏览器完成，**违反平台用户协议，有封号概率**。请先用小号验证，不要一上线就多平台、多账号、高频次。

开源项目的许可证只约束代码使用方式，不豁免平台条款。
