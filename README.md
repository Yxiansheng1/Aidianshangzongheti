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
① 选品   pick     候选池打分排序（数据你录入，模块只做判断）
        ↓
② 出图   gen      ComfyUI + Qwen-Image-Edit   0 元，约 8 分钟/张
        ↓
③ 出视频 vid      ComfyUI + Wan2.2 I2V        0 元，很慢
        ↓
④ 整理   输出目录（每个商品一个文件夹）
        ↓
⑤ 清单   ingest   读目录 → manifest.json
        ↓
⑥ 发布   publish  调 social-auto-upload → 抖音 / 小红书 / 快手 / 视频号
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

# 1. 选品：生成候选池 → 填 → 排序
python -m pipeline pick init
python -m pipeline pick rank --top 2

# 2. 出图：商品原图 → 场景主图
python -m pipeline gen --image "商品原图.png" `
    --prompt "放在浅色木纹桌面，清晨侧光，浅景深，商品保持原样"

# 3. 出视频：主图 → 短视频
python -m pipeline vid --image "商品原图-场景.png" `
    --prompt "镜头缓慢推进，光影缓慢变化"

# 4. 扫目录，生成发布清单
python -m pipeline ingest --dir "D:\MxPage\output"

# 5. 发布（默认只打印，不执行）
python -m pipeline publish --platform xiaohongshu --kind note
python -m pipeline publish --platform xiaohongshu --kind note --execute
```

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
