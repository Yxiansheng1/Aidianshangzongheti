"""生成三个候选「人设」：人设卡 + 头像（各 2 个方案）+ 一个预览页。

人设不是代码，是账号的脸。所以这里只出候选，不替 owner 决定。
挑定之后，把对应的人设卡拷成 pipeline/content/persona.md，
`rewrite` 会自动把它追加到每份平台 skill 后面（见 rewrite.py）。

跑法：python scripts\\make_personas.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, r"D:\AIdianshangzongheti")
sys.stdout.reconfigure(encoding="utf-8")

from pipeline.config import ROOT
from pipeline.model.comfyui import ComfyClient
from pipeline.text2img import Text2ImgConfig, generate

OUT = ROOT / "output" / "人设"

NEGATIVE = (
    "text, letters, words, watermark, logo, signature, caption, "
    "busy background, clutter, photo of a person, face closeup, "
    "lowres, blurry, deformed, jpeg artifacts, worst quality, "
    "gradient mesh, lens flare"
)

PERSONAS = [
    {
        "key": "A-老周在现场",
        "name": "老周在现场",
        "one_line": "把远处的技术新闻，翻成你手边的账。",
        "who": "25–40 岁，做技术的、开小生意的、关心钱怎么流动的人",
        "tone": "短句，先给数字再给判断，敢说「这个我查不到」",
        "boundary": "不吹融资额、不荐股、不替公司站台、不写自己没查过的东西",
        "bio_xhs": "写技术和钱。每条都给数字和来源，查不到就说查不到。",
        "bio_toutiao": "科技财经观察，只写查得到出处的数",
        "bio_baijia": "科技与财经事件解读，讲清数字背后的来龙去脉",
        "tags": ["科技观察", "财经解读", "数字说话"],
        "avatars": [
            {"file": "a1", "scene": "电台剪影",
             "prompt": "flat vector icon, a vintage radio receiver silhouette with a warm amber dial glowing, solid dark charcoal background, centered, bold simple shapes, high contrast, minimal, readable at small size"},
            {"file": "a2", "scene": "侧脸与耳机",
             "prompt": "flat vector icon, minimal silhouette of a man's side profile wearing headphones, warm amber accent line, solid dark charcoal background, centered, bold shapes, high contrast, minimal"},
        ],
    },
    {
        "key": "B-小满记账",
        "name": "小满记账",
        "one_line": "大新闻落到钱包上，到底是多少钱。",
        "who": "22–35 岁女性，刚工作几年，想搞明白钱去哪了",
        "tone": "第一人称，金额具体到个位，允许自嘲，不教训人",
        "boundary": "不推销产品、不制造焦虑、不教人借钱、不说「姐妹冲」",
        "bio_xhs": "把新闻算成钱。每月固定支出、房租、外卖，一笔一笔算给你看。",
        "bio_toutiao": "把大新闻算成普通人的账",
        "bio_baijia": "财经新闻里的数字，换算成普通家庭的实际收支",
        "tags": ["算账", "消费决策", "普通人的钱"],
        "avatars": [
            {"file": "b1", "scene": "账本与铅笔",
             "prompt": "flat vector icon, an open notebook with a pencil resting on it and two coins beside, warm cream background, centered, bold simple shapes, muted terracotta accent, high contrast, minimal"},
            {"file": "b2", "scene": "硬币与标签",
             "prompt": "flat vector icon, a small stack of coins with a price tag tied to it, warm cream background, centered, bold simple shapes, muted terracotta accent, high contrast, minimal"},
        ],
    },
    {
        "key": "C-夜读的人",
        "name": "夜读的人",
        "one_line": "每天读一条，说清它到底是什么。",
        "who": "想搞懂一件事、又不想被热搜带走的人",
        "tone": "克制，讲机制和前因后果，情绪放最后一句",
        "boundary": "不站队、不预测股价、不复述原文、不写「震惊」",
        "bio_xhs": "每天一条，把一件事读透：它是什么、怎么来的、跟你有什么关系。",
        "bio_toutiao": "每天一条，读透一件事的来龙去脉",
        "bio_baijia": "深度解读热点背后的机制与成因，不追情绪",
        "tags": ["深度解读", "读透一件事", "慢"],
        "avatars": [
            {"file": "c1", "scene": "台灯与手稿",
             "prompt": "flat vector icon, a desk lamp casting a warm pool of light on a few sheets of paper, deep navy background, centered, bold simple shapes, high contrast, minimal, calm mood"},
            {"file": "c2", "scene": "月与窗",
             "prompt": "flat vector icon, a simple window frame with a crescent moon and one warm lit window below, deep navy background, centered, bold simple shapes, high contrast, minimal"},
        ],
    },
]


def main() -> None:
    client = ComfyClient()
    if not client.is_up():
        raise SystemExit("ComfyUI 没在跑，先启动 启动工作台.bat")

    OUT.mkdir(parents=True, exist_ok=True)
    cfg = Text2ImgConfig(width=1024, height=1024, steps=24)
    made = 0

    for persona in PERSONAS:
        folder = OUT / persona["key"]
        folder.mkdir(parents=True, exist_ok=True)

        for avatar in persona["avatars"]:
            target = folder / f"avatar-{avatar['file']}.png"
            if target.is_file() and target.stat().st_size > 10000:
                print(f"[跳过] {target.name} 已存在")
                continue
            generate(client, avatar["prompt"] + ", no text, no letters",
                     target, cfg=cfg, seed=abs(hash(persona["key"] + avatar["file"])) % 100000,
                     negative=NEGATIVE)
            print(f"[生成] {persona['key']}/{target.name}  ({avatar['scene']})")
            made += 1

        # 人设卡
        card = [
            f"# {persona['name']}",
            "",
            f"**一句话**：{persona['one_line']}",
            "",
            "| 项 | 内容 |",
            "|---|---|",
            f"| 写给谁 | {persona['who']} |",
            f"| 语气 | {persona['tone']} |",
            f"| 不碰什么 | {persona['boundary']} |",
            f"| 标签 | {'、'.join(persona['tags'])} |",
            "",
            "## 简介（三平台各一版）",
            "",
            f"- **小红书**：{persona['bio_xhs']}",
            f"- **头条号**：{persona['bio_toutiao']}",
            f"- **百家号**：{persona['bio_baijia']}",
            "",
            "## 头像方案",
            "",
        ]
        for avatar in persona["avatars"]:
            card.append(f"### {avatar['scene']}")
            card.append("")
            card.append(f"![{avatar['scene']}](avatar-{avatar['file']}.png)")
            card.append("")
        (folder / "人设卡.md").write_text("\n".join(card), encoding="utf-8")

    # 预览页
    rows = []
    for persona in PERSONAS:
        base = persona["key"]
        avatars = "".join(
            f'<figure><img src="{base}/avatar-{a["file"]}.png"><figcaption>{a["scene"]}</figcaption></figure>'
            for a in persona["avatars"]
        )
        rows.append(f"""
        <section>
          <h2>{persona['name']}</h2>
          <p class="one">{persona['one_line']}</p>
          <div class="grid">{avatars}</div>
          <dl>
            <dt>写给谁</dt><dd>{persona['who']}</dd>
            <dt>语气</dt><dd>{persona['tone']}</dd>
            <dt>不碰什么</dt><dd>{persona['boundary']}</dd>
            <dt>小红书简介</dt><dd>{persona['bio_xhs']}</dd>
            <dt>头条 / 百家号</dt><dd>{persona['bio_toutiao']}　/　{persona['bio_baijia']}</dd>
          </dl>
        </section>""")

    html = f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>三个候选账号人设</title>
<style>
 body{{font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;background:#faf8f5;color:#22261f;margin:0;padding:32px}}
 h1{{font-size:22px;margin:0 0 6px}}
 .sub{{color:#7b8172;font-size:13px;margin-bottom:26px}}
 section{{background:#fff;border:1px solid #e6e2da;border-radius:12px;padding:20px 22px;margin-bottom:18px}}
 h2{{font-size:17px;margin:0 0 4px}}
 .one{{color:#4a5245;font-size:14px;margin:0 0 14px}}
 .grid{{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:14px}}
 figure{{margin:0;text-align:center}}
 img{{width:150px;height:150px;border-radius:50%;object-fit:cover;border:1px solid #e6e2da}}
 figcaption{{font-size:12px;color:#7b8172;margin-top:6px}}
 dl{{margin:0;font-size:13.5px;line-height:1.75}}
 dt{{float:left;width:96px;color:#7b8172}}
 dd{{margin:0 0 4px 100px}}
</style>
<h1>三个候选：人设 + 头像</h1>
<p class="sub">头像 1024×1024，圆形成品预览就是这个大小。挑一个方向（也可以混搭：A 的名字 + C 的头像），我再细化。</p>
{''.join(rows)}
</html>"""
    (OUT / "预览.html").write_text(html, encoding="utf-8")

    print(f"\n生成 {made} 张头像。产物：{OUT}")
    print("预览：", OUT / "预览.html")


if __name__ == "__main__":
    main()
