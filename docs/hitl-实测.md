# 人工审批（HITL）实测结论

> 这份是踩出来的，不是抄文档。环境：`deepagents 0.7.32` + `langchain 1.4.9` + `langgraph 1.2.20`，
> 模型 `deepseek-v4-pro`（tokenav 网关），验证脚本 `scripts/harness_smoke_model.py`。

## 一、闸门怎么配

`create_deep_agent(interrupt_on={...})`，值是 `bool` 或 `InterruptOnConfig`：

```python
interrupt_on={
    "check_status": False,       # 只读，不停
    "publish_article": True,     # 停，等审批
}
```

我们的 `pipeline/harness/agent.py::_interrupt_on()` 按三档自主度自动生成这个字典，
不需要手写。

## 二、停下来时长什么样（实测）

```python
interrupt.value = {
  "action_requests": [
    {
      "name": "publish_article",
      "args": {"title": "测试稿"},
      "description": "Tool execution requires approval\n\nTool: publish_article\nArgs: {...}",
    }
  ],
  "review_configs": [
    {
      "action_name": "publish_article",
      "allowed_decisions": ["approve", "edit", "reject", "respond"],
    }
  ],
}
```

四种决策：**approve（照原样执行）/ edit（改参数再执行）/ reject（不执行）/ respond（直接回一句话当结果）**。

## 三、恢复格式（这里踩了三次坑）

```python
from langgraph.types import Command
agent.invoke(Command(resume={"decisions": {0: {"type": "approve"}}}), config=config)
```

- `decisions` 的键是 **`action_requests` 的序号（0,1,2…）**，不是 `interrupt.id`
- 试过但**不行**的：`{interrupt_id: {...}}`（KeyError: 'decisions'）、`{"type": "approve"}`（同上）、`True`（同上）、`{"decisions": [...]}`（KeyError: 0）
- 多条动作就一次全给：`{"decisions": {0: {...}, 1: {...}}}`

界面侧不用记这些细节，用 `pipeline.harness.approval`：

```python
from pipeline.harness.approval import parse_interrupt, approve_all, reject_all

pending = parse_interrupt(interrupt)   # 拿到 [(序号, 工具名, 参数, 可选决策)]
payload = approve_all(pending)         # 一键同意
payload = reject_all(pending, "标题要改")
```

## 四、两个必须知道的实现约束

**① 必须有 checkpointer，而且不能传 `True`**

```python
create_deep_agent(..., checkpointer=InMemorySaver())   # 根图必须给真实 saver
# checkpointer=True → RuntimeError: checkpointer=True cannot be used for root graphs.
```

`InMemorySaver` 进程退出就丢；要跨重启，换 `SqliteSaver`（下一轮接）。

**② 恢复时被中断的那个节点会从头重跑**

所以：**审批节点里不要放副作用**。发邮件、扣款、发布这些动作，要放在审批之后的独立节点/工具里，
否则批准一次会执行两次——这是这类框架的通用坑，不是 Deep Agents 特有。

## 五、实测输出（原文照抄）

```
闸门配置： {'check_status': False, 'publish_article': True}
--- 第一次调用（应停在 publish_article 前）---
interrupt id: e5f1accd6a5671575a68615c9f24a439
审批载荷： {'action_requests': [{'name': 'publish_article', 'args': {'title': '测试稿'}, ...}], ...}
✅ 恢复格式「decisions 用序号 0」有效
最终回复： 已发布完成。
- **状态检查**：草稿已写好 · 标题《测试稿》 · 正文 800 字 · 等待发布
- **发布结果**：已发布：测试稿
```

## 六、下一步

1. 接 `SqliteSaver`，让审批能跨进程重启（客户端关掉再开，还能接着批）
2. 把 `approval.py` 的三件套接到 L3 的界面：`/api/tools` 已经带 risk/critical，弹窗直接用 `PendingApproval`
3. 解决 `fill_editor` 的 `input()` 问题（L2 交回里报的头号雷）
