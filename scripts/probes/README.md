# scripts/probes/ — 历史试错脚本

这些是开发过程中临时写的一次性验证脚本（文件名以下划线开头）。
**不是正式入口**，留着只为追溯"当时是怎么确认的"。

正式工具在 `scripts/` 根目录：

| 脚本 | 用途 |
|---|---|
| `harness_check.py` | 看三档自主度下的审批闸门（不需要模型） |
| `harness_smoke_model.py` | 真模型验证「停→批→续」 |
| `harness_accept.py` | 收货抽查：工具注册表 + API 对接 |
| `e2e_task.py` | 端到端：交任务 → 轮询 → 看结果 |
| `publish_toutiao.py` | 填进头条编辑器（可选点发布） |
| `add_toutiao_topics.py` | 给已发文章补真话题 |
| `set_toutiao_profile.py` | 填头条账号资料 |
| `check_toutiao_accounts.py` / `check_baijiahao_accounts.py` | 核对账号身份（防两个号登成同一个） |
| `check_articles.py` / `check_article_public.py` / `check_article_topics.py` | 查文章状态与话题 |
| `check_toutiao_publish_rights.py` | 查发布权限 |
| `baidu_suggest.py` | 查百度下拉词（百家号选题用） |
| `build_history_topics.py` | 建历史题库 |
| `make_account_profiles.py` / `make_personas*.py` | 生成账号资料与人设 |
| `test_pipeline.py` / `test_platforms.py` / `test_publish.py` | 内容线横评与校验 |

注意：`probes/` 里的脚本可能在结构重构后已经跑不通，别拿它们当入口。
