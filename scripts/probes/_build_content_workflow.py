"""生成「内容生产流水线」n8n 工作流。

设计原则：**逻辑全部在画布上可见**，不藏在外部 API 里。

所以每个环节都是一类节点：
    Set    提示词写在这里，点开就能读、能改
    HTTP   直接调 tokenav / ComfyUI，没有中间层
    Code   解析和判断，JS 摆在画布上
    IF     分支
    Wait   等待轮询

对比之前那条「电商·出图→出视频」：那条把逻辑放在 Python 能力层，
画布上只有触发器，适合生产但学不到东西。这条相反。

流程：
    手动开始 → 参数 → 拼写稿提示词 → 写稿(HTTP) → 解析稿件(Code)
    → 拼审核提示词 → 审核(HTTP) → 解析审核(Code) → 有必改项?(IF)
        ├ 有 → 退回待改
        └ 无 → 提交出图(HTTP) → 等20秒 → 查图状态(HTTP) → 图完成?(IF)
                                              ↑                    │
                                              └──── 没好 ──────────┘
                                                                   ↓
                                                                 完成
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "workflows" / "内容生产流水线.json"

UA_CRED = {"httpHeaderAuth": {"id": "KR6jN1SBltiLYYST", "name": "tokenav Bearer"}}
LLM_URL = "https://www.tokenav.ai/v1/chat/completions"
MODEL = "deepseek-v4-pro"
BASE = "http://127.0.0.1:8899"


def nid() -> str:
    return str(uuid.uuid4())


def node(name, ntype, version, pos, params=None, notes=None, credentials=None):
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
    if credentials:
        item["credentials"] = credentials
    return item


def llm_node(name, pos, notes=None):
    """调 tokenav 的 HTTP 节点。提示词来自上一个 Set 节点的 system / user。"""
    return node(
        name, "n8n-nodes-base.httpRequest", 4.2, pos,
        {
            "method": "POST",
            "url": LLM_URL,
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": (
                "={{ JSON.stringify({ model: '" + MODEL + "', "
                "messages: [ { role: 'system', content: $json.system }, "
                "{ role: 'user', content: $json.user } ], "
                "temperature: 0.6, max_tokens: 4000 }) }}"
            ),
            "options": {"timeout": 180000},
        },
        notes,
        UA_CRED,
    )


def setter(name, pairs, pos, notes=None):
    return node(
        name, "n8n-nodes-base.set", 3.4, pos,
        {
            "assignments": {
                "assignments": [
                    {"id": nid(), "name": k, "value": v, "type": "string"}
                    for k, v in pairs
                ]
            },
            "options": {},
        },
        notes,
    )


nodes = [
    node("手动开始", "n8n-nodes-base.manualTrigger", 1, (0, 320),
         notes="点上面的 Execute workflow 开始"),

    setter("参数", [
        ("topic", "香氛 年轻人的情绪搭子"),
        ("platform", "xiaohongshu"),
        ("product", "渐变杯装香薰蜡烛，大豆蜡，燃烧约25小时"),
        ("sourceImage", "D:/AIdianshangzongheti/input_uploads/1793178507-0621.jpg_wh860.jpg"),
        ("publish", "no"),
    ], (200, 320), notes="跑之前改这里。publish 填 yes 才会真的发出去，默认 no 只跑到出图。"),

    setter("拼写稿提示词", [
        ("system",
         "你是中文内容编辑，写给真实的人看。只说事实和真实感受，"
         "不编造数据、不写绝对化用语、不用夸张营销腔。"
         "输出必须是合法 JSON：{\"title\":\"\",\"body\":\"\",\"tags\":[]}，不要代码围栏。"),
        ("user",
         "=平台：" + "{{ $('参数').first().json.platform }}" + "\n"
         "主题：" + "{{ $('参数').first().json.topic }}" + "\n"
         "商品：" + "{{ $('参数').first().json.product }}" + "\n\n"
         "写作要求：\n"
         "- 小红书：第一人称、口语、短句分段，150-300 字，标题≤20字，标签≤8个\n"
         "- 知乎：理性、分小标题，400-800 字，标题≤60字\n"
         "- 百家号：资讯体、客观、利搜索，500-800 字，标题≤30字\n"
         "- 抖音：口播稿，前3秒抓人，一句一行，150-200 字\n\n"
         "禁写：最/第一/100%/治愈/根治/加微信/点击链接。"),
    ], (420, 320), notes="提示词就在这个节点里，双击可改。改完直接跑。"),

    llm_node("写稿", (640, 320), notes="调 tokenav 的 deepseek-v4-pro"),

    node("解析稿件", "n8n-nodes-base.code", 2, (860, 320), {
        "jsCode": (
            "const raw = $input.first().json;\n"
            "const content = raw.choices?.[0]?.message?.content ?? '';\n"
            "let data;\n"
            "try {\n"
            "  const m = content.match(/```(?:json)?\\s*([\\s\\S]*?)```/);\n"
            "  data = JSON.parse(m ? m[1] : content);\n"
            "} catch (e) {\n"
            "  throw new Error('写稿节点返回的不是 JSON：' + content.slice(0, 300));\n"
            "}\n"
            "return [{ json: {\n"
            "  title: data.title || '',\n"
            "  body: data.body || '',\n"
            "  tags: (data.tags || []).join(','),\n"
            "  platform: $('参数').first().json.platform\n"
            "} }];"
        )
    }, notes="从 choices[0].message.content 里抠 JSON，抠不出来就报错停下"),

    setter("拼审核提示词", [
        ("system",
         "你是内容合规审核员。只判断不改写。输出合法 JSON，不要代码围栏。"),
        ("user",
         "=审核这段要发到 {{ $('参数').first().json.platform }} 的文案。\n\n"
         "先把它拆成可核查的事实性表述（数字、材质、效果承诺、对比结论、销量评价）。\n"
         "**不要拆**主观感受、修辞、场景描写、提问。\n\n"
         "然后逐条判断：属实 / 存疑 / 无法证实 / 夸大 / 主观\n"
         "- 无法证实：涉及具体数据但没来源\n"
         "- 夸大：把普通商品说成功效产品\n"
         "- 主观：个人感受，不算问题\n\n"
         "文案：\n\"\"\"\n"
         "{{ $json.title }}\n\n{{ $json.body }}\n"
         "\"\"\"\n\n"
         "输出 JSON：\n"
         "{\"passed\": true/false, \"score\": 0-100, \"issues\":"
         " [{\"level\":\"block 或 warn\",\"claim\":\"\",\"advice\":\"\"}], \"summary\":\"\"}\n\n"
         "有任意 block 就是 passed=false。"),
    ], (1080, 320), notes="审核标准也写在节点里，可以自己调松紧"),

    llm_node("审核", (1300, 320)),

    node("解析审核", "n8n-nodes-base.code", 2, (1520, 320), {
        "jsCode": (
            "const raw = $input.first().json;\n"
            "const content = raw.choices?.[0]?.message?.content ?? '';\n"
            "let data;\n"
            "try {\n"
            "  const m = content.match(/```(?:json)?\\s*([\\s\\S]*?)```/);\n"
            "  data = JSON.parse(m ? m[1] : content);\n"
            "} catch (e) {\n"
            "  data = { passed: false, score: 0, issues: [{ level: 'block', claim: '', advice: '审核返回格式异常，人工看一看' }], summary: '解析失败' };\n"
            "}\n"
            "const issues = data.issues || [];\n"
            "const blocks = issues.filter(i => i.level === 'block');\n"
            "return [{ json: {\n"
            "  passed: blocks.length === 0 && data.passed !== false,\n"
            "  score: data.score ?? 0,\n"
            "  summary: data.summary || '',\n"
            "  blocks: blocks.length,\n"
            "  issuesText: issues.map(i => `[${i.level}] ${i.claim || ''} -> ${i.advice || ''}`).join('\\n'),\n"
            "  title: $('解析稿件').first().json.title,\n"
            "  body: $('解析稿件').first().json.body,\n"
            "  tags: $('解析稿件').first().json.tags,\n"
            "  sourceImage: $('参数').first().json.sourceImage\n"
            "} }];"
        )
    }, notes="只要有一处 block 就判不通过"),

    node("有必改项?", "n8n-nodes-base.if", 2, (1740, 320), {
        "conditions": {
            "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
            "conditions": [{
                "id": nid(),
                "leftValue": "={{ $json.passed }}",
                "rightValue": True,
                "operator": {"type": "boolean", "operation": "true", "singleValue": True},
            }],
            "combinator": "and",
        },
        "options": {},
    }, notes="passed=true 走上面（继续出图），false 走下面（退回改）"),

    setter("退回待改", [
        ("verdict", "=不通过（{{ $json.score }} 分）：{{ $json.summary }}"),
        ("problems", "={{ $json.issuesText }}"),
    ], (1960, 480), notes="这一步停住。改完文案重新跑。"),

    node("提交出图", "n8n-nodes-base.httpRequest", 4.2, (1960, 220), {
        "method": "POST",
        "url": f"{BASE}/api/gen",
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": (
            "={{ JSON.stringify({ "
            "source: $json.sourceImage, "
            "prompt: '把商品放在浅色木纹桌面上，清晨柔和侧光，浅景深，商品保持原样不变形', "
            "size: 1024 }) }}"
        ),
        "options": {"timeout": 60000},
    }, notes="调本地工作台的 ComfyUI 出图，立刻返回 job.id"),

    node("等20秒", "n8n-nodes-base.wait", 1.1, (2180, 220), {
        "resume": "timeInterval", "amount": 20, "unit": "seconds",
    }, notes="8GB 显存一张约 7 分钟，会循环二十多次"),

    node("查图状态", "n8n-nodes-base.httpRequest", 4.2, (2400, 220), {
        "method": "GET",
        "url": "=" + BASE + "/api/job?id={{ $('提交出图').first().json.job.id }}",
        "options": {"timeout": 30000},
    }),

    node("图完成?", "n8n-nodes-base.if", 2, (2620, 220), {
        "conditions": {
            "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
            "conditions": [{
                "id": nid(),
                "leftValue": "={{ $json.status }}",
                "rightValue": "done",
                "operator": {"type": "string", "operation": "equals"},
            }],
            "combinator": "and",
        },
        "options": {},
    }, notes="没好就回到等20秒，好了往下走"),

    setter("完成", [
        ("verdict", "=通过（{{ $('解析审核').first().json.score }} 分）"),
        ("image", "={{ $json.result.path }}"),
        ("title", "={{ $('解析审核').first().json.title }}"),
        ("body", "={{ $('解析审核').first().json.body }}"),
        ("tags", "={{ $('解析审核').first().json.tags }}"),
        ("platform", "={{ $('参数').first().json.platform }}"),
        ("publish", "={{ $('参数').first().json.publish }}"),
    ], (2840, 220), notes="素材齐了。接下来按 publish 决定发不发。"),

    node("要发布吗", "n8n-nodes-base.if", 2, (3060, 220), {
        "conditions": {
            "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
            "conditions": [{
                "id": nid(),
                "leftValue": "={{ $json.publish }}",
                "rightValue": "yes",
                "operator": {"type": "string", "operation": "equals"},
            }],
            "combinator": "and",
        },
        "options": {},
    }, notes="参数里 publish 填 yes 才走上面。默认 no，不会误发。"),

    node("发布到小红书", "n8n-nodes-base.executeCommand", 1, (3280, 120), {
        "command": (
            "=\"D:/social-auto-upload/.venv/Scripts/sau.exe\" xiaohongshu upload-note "
            "--account main "
            "--images \"{{ $json.image }}\" "
            "--title \"{{ $json.title }}\" "
            "--note \"{{ $json.body }}\" "
            "--tags \"{{ $json.tags }}\" "
            "--headed"
        )
    }, notes="真的发出去。注意 --headed：无头模式容易被平台识别为自动化"),

    setter("发布完成", [
        ("结果", "={{ $json.stdout }}"),
    ], (3500, 120), notes="看 stdout，出现「图文发布成功」就是发出去了"),

    setter("跳过发布", [
        ("结果", "=参数里 publish = no，只出了图，没发布。image={{ $json.image }}"),
    ], (3280, 340), notes="默认走这条，安全"),
]


def link(src, targets):
    out = []
    for target in targets:
        out.append([{"node": target, "type": "main", "index": 0}] if target else [])
    return src, {"main": out}


connections = dict([
    link("手动开始", ["参数"]),
    link("参数", ["拼写稿提示词"]),
    link("拼写稿提示词", ["写稿"]),
    link("写稿", ["解析稿件"]),
    link("解析稿件", ["拼审核提示词"]),
    link("拼审核提示词", ["审核"]),
    link("审核", ["解析审核"]),
    link("解析审核", ["有必改项?"]),
    link("有必改项?", ["提交出图", "退回待改"]),
    link("提交出图", ["等20秒"]),
    link("等20秒", ["查图状态"]),
    link("查图状态", ["图完成?"]),
    link("图完成?", ["完成", "等20秒"]),
    link("完成", ["要发布吗"]),
    link("要发布吗", ["发布到小红书", "跳过发布"]),
])

workflow = {
    "name": "内容生产流水线（全画布可见）",
    "nodes": nodes,
    "connections": connections,
    "settings": {"executionOrder": "v1"},
    "active": False,
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"已生成 {OUT}")
print(f"节点 {len(nodes)} 个，连接 {len(connections)} 组")
