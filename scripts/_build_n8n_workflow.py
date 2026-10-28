"""生成 n8n 工作流 JSON。

为什么用脚本生成而不是手写 JSON：节点之间有十几条连接，手写容易错位，
而且改一次布局就要重排。生成器只描述「有哪些节点、谁连谁」。

流程：
    参数 → 提交出图 → 轮询(等20s/查状态/失败?/完成?) → 出图结果
         → 提交视频 → 轮询(等60s/查状态/失败?/完成?) → 完成

轮询用「Wait + IF 回连」实现，所以流程里有一个环。n8n 支持这种回环，
但要注意：任务出错必须能跳出，否则会无限循环。
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

BASE = "http://127.0.0.1:8899"
OUT = Path(__file__).resolve().parent.parent / "workflows" / "ecom-gen-video.json"


def nid() -> str:
    return str(uuid.uuid4())


def node(name, ntype, version, pos, params=None, notes=None):
    item = {
        "parameters": params or {},
        "id": nid(),
        "name": name,
        "type": ntype,
        "typeVersion": version,
        "position": list(pos),
    }
    if notes:
        item["notes"] = notes
        item["notesInFlow"] = True
    return item


def http(name, method, url, pos, body=None, notes=None):
    params = {
        "method": method,
        "url": url,
        "options": {"timeout": 120000},
    }
    if body is not None:
        params["sendBody"] = True
        params["specifyBody"] = "json"
        params["jsonBody"] = body
    return node(name, "n8n-nodes-base.httpRequest", 4.2, pos, params, notes)


def setter(name, assignments, pos, notes=None):
    return node(
        name,
        "n8n-nodes-base.set",
        3.4,
        pos,
        {
            "assignments": {
                "assignments": [
                    {"id": nid(), "name": k, "value": v, "type": "string"}
                    for k, v in assignments
                ]
            },
            "options": {},
        },
        notes,
    )


def ifnode(name, left, op, right, pos, notes=None):
    return node(
        name,
        "n8n-nodes-base.if",
        2,
        pos,
        {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                "conditions": [
                    {
                        "id": nid(),
                        "leftValue": left,
                        "rightValue": right,
                        "operator": {"type": "string", "operation": op},
                    }
                ],
                "combinator": "and",
            },
            "options": {},
        },
        notes,
    )


def wait(name, seconds, pos, notes=None):
    return node(
        name,
        "n8n-nodes-base.wait",
        1.1,
        pos,
        {"resume": "timeInterval", "amount": seconds, "unit": "seconds"},
        notes,
    )


nodes = [
    node("手动开始", "n8n-nodes-base.manualTrigger", 1, (0, 300),
         notes="点上面的 Execute workflow 开始"),

    setter("参数", [
        ("source", "D:\\AIdianshangzongheti\\input_uploads\\在这里填图片绝对路径.png"),
        ("imagePrompt", "把商品放在浅色木纹桌面上，清晨柔和侧光，浅景深，背景轻微虚化，商品保持原样不变形"),
        ("videoPrompt", "镜头缓慢推进，光线缓缓移动，画面安静高级"),
        ("size", "1024"),
    ], (200, 300), notes="跑之前改这里：原图路径 + 两个提示词"),

    http("提交出图", "POST", f"{BASE}/api/gen", (420, 300),
         body="={{ JSON.stringify({ source: $json.source, prompt: $json.imagePrompt, size: parseInt($json.size) }) }}",
         notes="异步任务，立刻返回 job.id"),

    setter("记图任务", [("jobId", "={{ $json.job.id }}")], (640, 300)),

    wait("等图20秒", 20, (860, 300), notes="8GB 显存大约要 8 分钟，会循环二十多次"),

    http("查图状态", "GET",
         "=" + BASE + "/api/job?id={{ $('记图任务').item.json.jobId }}", (1080, 300)),

    ifnode("图失败?", "={{ $json.status }}", "equals", "error", (1300, 300)),

    ifnode("图完成?", "={{ $json.status }}", "equals", "done", (1300, 420)),

    node("停-出图失败", "n8n-nodes-base.noOp", 1, (1520, 300)),

    setter("出图结果", [("imagePath", "={{ $json.result.path }}")], (1520, 420)),

    http("提交视频", "POST", f"{BASE}/api/vid", (1740, 420),
         body="={{ JSON.stringify({ source: $json.imagePath, prompt: $('参数').item.json.videoPrompt }) }}"),

    setter("记视频任务", [("jobId", "={{ $json.job.id }}")], (1960, 420)),

    wait("等视频60秒", 60, (2180, 420), notes="视频更慢，双 14B 模型接力，可能要半小时"),

    http("查视频状态", "GET",
         "=" + BASE + "/api/job?id={{ $('记视频任务').item.json.jobId }}", (2400, 420)),

    ifnode("视频失败?", "={{ $json.status }}", "equals", "error", (2620, 420)),

    ifnode("视频完成?", "={{ $json.status }}", "equals", "done", (2620, 540)),

    node("停-视频失败", "n8n-nodes-base.noOp", 1, (2840, 420)),

    setter("完成", [
        ("image", "={{ $('出图结果').item.json.imagePath }}"),
        ("video", "={{ $json.result.path }}"),
    ], (2840, 540)),
]


def link(src, targets):
    """targets: 按输出索引排列，每个元素是目标节点名或 None。"""
    out = []
    for target in targets:
        out.append([{"node": target, "type": "main", "index": 0}] if target else [])
    return src, {"main": out}


connections = dict([
    link("手动开始", ["参数"]),
    link("参数", ["提交出图"]),
    link("提交出图", ["记图任务"]),
    link("记图任务", ["等图20秒"]),
    link("等图20秒", ["查图状态"]),
    link("查图状态", ["图失败?"]),
    # IF 输出 0 = true，1 = false
    link("图失败?", ["停-出图失败", "图完成?"]),
    link("图完成?", ["出图结果", "等图20秒"]),
    link("出图结果", ["提交视频"]),
    link("提交视频", ["记视频任务"]),
    link("记视频任务", ["等视频60秒"]),
    link("等视频60秒", ["查视频状态"]),
    link("查视频状态", ["视频失败?"]),
    link("视频失败?", ["停-视频失败", "视频完成?"]),
    link("视频完成?", ["完成", "等视频60秒"]),
])

workflow = {
    "name": "电商 · 出图→出视频",
    "nodes": nodes,
    "connections": connections,
    "settings": {"executionOrder": "v1"},
    "active": False,
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"已生成 {OUT}")
print(f"节点 {len(nodes)} 个，连接 {len(connections)} 组")
