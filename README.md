# AI 电商综合体

从「一个商品」到「多平台可发布内容」的本地流水线。

**定位：从找到一个品，到发出第一批内容，30 分钟。**

---

## 现状

当前是**第 0 步：骨架**。核心的生成与发布能力全部复用成熟开源项目，本仓库只负责中间那层胶水。

| 层 | 用什么 | 许可证 | 状态 |
|---|---|---|---|
| 模型网关 | [one-api](https://github.com/songquanpeng/one-api) | MIT | 第二阶段（可选） |
| 内容生成 | [MxPage](https://github.com/ziguishian/MxPage) | MIT | 待安装 |
| 多平台发布 | [social-auto-upload](https://github.com/dreammis/social-auto-upload) | MIT | 待安装 |
| 选品数据 | 暂不做 | — | 后续 |
| **胶水层** | **本仓库** | 私有 | 开发中 |

## 拼装关系

```
商品图 / 商品事实
        ↓
    MxPage（生成主图、详情页、小红书图文）
        ↓
    输出目录（每个商品一个文件夹）
        ↓
    ingest  读目录 → 生成 manifest.json
        ↓
    model   可选：润色标题 / 正文 / 标签
        ↓
    publish 调 social-auto-upload 的 CLI
        ↓
    抖音 / 小红书 / 快手 / 视频号
```

**设计原则：`model` 和 `publish` 都是适配层。** 换模型供应商只改 `config.toml`，换发布工具只改 `pipeline/publish/`，主流程不动。

## 快速开始

```powershell
cd D:\AIdianshangzongheti
python -m pipeline check
```

三条命令就能跑完全流程：

```powershell
python -m pipeline check                                   # 环境自检
python -m pipeline ingest --dir "D:\MxPage\output"          # 扫描产物，生成清单
python -m pipeline publish --platform xiaohongshu           # 打印发布计划（默认不执行）
python -m pipeline publish --platform xiaohongshu --execute # 真正执行
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
