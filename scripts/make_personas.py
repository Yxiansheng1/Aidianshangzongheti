"""生成候选「人设」：人设卡 + 头像（各 2 个）+ 一张对比预览页。

人设不是代码，是账号的脸，所以只出候选、不替你拍板。
挑定之后用界面的「人设」下拉，或直接把对应的人设卡拷成
pipeline/content/persona.md（rewrite 会自动追加到每份平台 skill 后面）。

    python scripts\\make_personas.py          # 补齐缺的头像 + 重出预览页
    python scripts\\make_personas.py --force   # 全部重画
"""
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
        "sample": "Intel 一夜跌掉两成。市场不是在罚已经发生的事，是在给下季度重新定价。",
        "fit": "头条、百家号为主；小红书要转成「我用它做了什么」",
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
        "sample": "Intel 跌两成，跟我有什么关系？去年买两万，今天剩一万六。",
        "fit": "小红书为主；头条财经版能发",
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
        "sample": "Intel 这一跌，跌的不是一件事，是三件叠在一起：换机周期、代工烧钱、AI 掉队。",
        "fit": "头条深度、百家号搜索长尾；小红书偏慢",
        "bio_xhs": "每天一条，把一件事读透：它是什么、怎么来的、跟你有什么关系。",
        "bio_toutiao": "每天一条，读透一件事的来龙去脉",
        "bio_baijia": "深度解读热点背后的机制与成因，不追情绪",
        "tags": ["深度解读", "读透一件事", "慢"],
        "avatars": [
            {"file": "c1", "scene": "台灯与手稿",
             "prompt": "flat vector icon, a desk lamp casting a warm pool of light on a few sheets of paper, deep navy background, centered, bold simple shapes, high contrast, minimal, calm mood"},
            {"file": "c2", "scene": "夜窗",
             "prompt": "flat vector icon, a single arched window frame at night, one crescent moon and five small stars in a deep navy sky, warm amber window frame, centered, bold simple shapes, high contrast, minimal"},
        ],
    },
    {
        "key": "D-工位观察员",
        "name": "工位观察员",
        "one_line": "大新闻落到工位上，最先疼的是谁。",
        "who": "一线城市打工的人，25–35 岁，关心公司、裁员、工资、行业风向",
        "tone": "毒舌但克制，专挑「没人愿意先说的那句话」，不骂人、不煽动",
        "boundary": "不点名具体公司员工、不编内部消息、不教人对抗公司、不制造恐慌",
        "sample": "Intel 跌两成。最先有感觉的不是股民，是下周要去面这家的人。",
        "fit": "小红书、头条都很吃；评论区活跃",
        "bio_xhs": "写公司里那些没人愿意先说的实话。看完不一定舒服，但不骗你。",
        "bio_toutiao": "职场与行业观察，说点公司不爱听的话",
        "bio_baijia": "从新闻看职场变化：哪些岗位在缩、哪些在涨",
        "tags": ["职场观察", "行业风向", "说点实话"],
        "avatars": [
            {"file": "d1", "scene": "工位与咖啡",
             "prompt": "flat vector icon, a minimal office desk partition with a takeaway coffee cup and a hanging badge lanyard, cool grey background, centered, bold simple shapes, one warm accent color, high contrast, minimal"},
            {"file": "d2", "scene": "工牌",
             "prompt": "flat vector icon, a blank staff badge on a lanyard hanging straight down, cool grey background, centered, bold simple shapes, one warm accent color, high contrast, minimal, no text"},
        ],
    },
    {
        "key": "E-拆解局",
        "name": "拆解局",
        "one_line": "不评价好坏，先把它拆开看清楚。",
        "who": "爱看「这东西怎么造出来的」的人，动手派、工程师、爱好者",
        "tone": "讲工序和结构，句子短，用具体数字和零件名，不抒情",
        "boundary": "不吹参数、不做云评测（没用过就不说手感）、不搬运他人拆解图",
        "sample": "一颗 GPU 从晶圆到装进显卡要过九百多道工序，21% 的跌幅只是最后那道。",
        "fit": "小红书（图好看）、B站/抖音（要视频）；头条偏硬",
        "bio_xhs": "拆开看：这东西怎么造出来的、为什么贵、贵在哪一步。",
        "bio_toutiao": "拆解技术工艺：从原料到成品，中间发生了什么",
        "bio_baijia": "技术原理与制造工艺科普，讲清步骤和成本构成",
        "tags": ["拆解", "制造工艺", "原理"],
        "avatars": [
            {"file": "e1", "scene": "螺丝刀与零件",
             "prompt": "flat vector icon, a precision screwdriver crossed with a small circuit board and three loose screws, slate blue background, centered, bold simple shapes, steel grey and one orange accent, high contrast, minimal"},
            {"file": "e2", "scene": "爆炸视图",
             "prompt": "flat vector icon, an exploded view of a small machine with three separated layers floating apart, slate blue background, centered, bold simple shapes, steel grey and one orange accent, high contrast, minimal"},
        ],
    },
    {
        "key": "F-只说结论",
        "name": "只说结论",
        "one_line": "三句话说完，剩下你自己判断。",
        "who": "没耐心看长文、只想知道「所以呢」的人",
        "tone": "极简，每段一句，先结论后原因，不留废话，不寒暄",
        "boundary": "不写过程、不抒情、不引用大段原文；结论必须有依据否则不写",
        "sample": "Intel 跌 21%。原因：代工还在烧钱，换机周期见底。我的判断：下一季还会再跌一轮。",
        "fit": "小红书、抖音、微博；头条撑不住长文",
        "bio_xhs": "三句话讲完一条新闻：发生了什么、为什么、我的判断。",
        "bio_toutiao": "只说结论的新闻速览",
        "bio_baijia": "简明新闻解读：一句话结论 + 三条依据",
        "tags": ["三句话", "结论先行", "速览"],
        "avatars": [
            {"file": "f1", "scene": "大句号",
             "prompt": "flat vector icon, one large bold full stop punctuation mark on a clean off-white background, solid black with a single red dot accent, centered, geometric, high contrast, minimal, no text"},
            {"file": "f2", "scene": "三条线",
             "prompt": "flat vector icon, three short horizontal bars stacked and aligned left, one bar highlighted in red, clean off-white background, centered, geometric, high contrast, minimal, no text"},
        ],
    },
]


def avatar_prompt(prompt: str) -> str:
    return prompt + ", no text, no letters"


def main() -> None:
    force = "--force" in sys.argv

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
            if target.is_file() and target.stat().st_size > 10000 and not force:
                print(f"[跳过] {target.name}")
                continue
            generate(client, avatar_prompt(avatar["prompt"]), target, cfg=cfg,
                     seed=abs(hash(persona["key"] + avatar["file"])) % 100000,
                     negative=NEGATIVE)
            print(f"[生成] {persona['key']}/{target.name}（{avatar['scene']}）")
            made += 1

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
            f"| 适合平台 | {persona['fit']} |",
            f"| 标签 | {'、'.join(persona['tags'])} |",
            "",
            "## 他会怎么写这条新闻",
            "",
            f"> {persona['sample']}",
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
            card += [f"### {avatar['scene']}", "", f"![{avatar['scene']}](avatar-{avatar['file']}.png)", ""]
        (folder / "人设卡.md").write_text("\n".join(card), encoding="utf-8")

    sections = []
    for p in PERSONAS:
        base = p["key"]
        avatars = "".join(
            f'<figure><img src="{base}/avatar-{a["file"]}.png"><figcaption>{a["scene"]}</figcaption></figure>'
            for a in p["avatars"]
        )
        sections.append(f"""
        <section>
          <div class="head">
            <h2>{p['name']}</h2>
            <span class="tag">{p['fit']}</span>
          </div>
          <p class="one">{p['one_line']}</p>
          <div class="grid">{avatars}</div>
          <blockquote>{p['sample']}</blockquote>
          <dl>
            <dt>写给谁</dt><dd>{p['who']}</dd>
            <dt>语气</dt><dd>{p['tone']}</dd>
            <dt>不碰什么</dt><dd>{p['boundary']}</dd>
            <dt>小红书简介</dt><dd>{p['bio_xhs']}</dd>
          </dl>
        </section>""")

    html = f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>六个候选账号人设</title>
<style>
 body{{font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;background:#faf8f5;color:#22261f;margin:0;padding:32px 34px}}
 h1{{font-size:22px;margin:0 0 6px}}
 .sub{{color:#7b8172;font-size:13px;margin-bottom:24px;line-height:1.7}}
 section{{background:#fff;border:1px solid #e6e2da;border-radius:12px;padding:18px 20px;margin-bottom:16px}}
 .head{{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}}
 h2{{font-size:17px;margin:0}}
 .tag{{font-size:11.5px;color:#8a6a3f;background:#f6efe4;border-radius:99px;padding:2px 10px}}
 .one{{color:#4a5245;font-size:14px;margin:6px 0 12px}}
 .grid{{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:12px}}
 figure{{margin:0;text-align:center}}
 img{{width:132px;height:132px;border-radius:50%;object-fit:cover;border:1px solid #e6e2da}}
 figcaption{{font-size:11.5px;color:#7b8172;margin-top:6px}}
 blockquote{{margin:0 0 12px;padding:10px 14px;background:#f7f5f0;border-left:3px solid #d8cfbe;font-size:14px;line-height:1.75;border-radius:0 6px 6px 0}}
 dl{{margin:0;font-size:13px;line-height:1.7}}
 dt{{float:left;width:88px;color:#7b8172}}
 dd{{margin:0 0 3px 96px}}
</style>
<h1>六个候选：人设 + 头像</h1>
<p class="sub">
每个人设下面都写了「同一条新闻他会怎么写」，比名字有用。<br>
挑一两个（可以混搭：A 的身份 + C 的头像），我把首图模板、文末签名、账号资料表补齐。
</p>
{''.join(sections)}
</html>"""
    (OUT / "预览.html").write_text(html, encoding="utf-8")

    print(f"\n新生成 {made} 张头像，共 {len(PERSONAS)} 个人设。")
    print("预览：", OUT / "预览.html")


if __name__ == "__main__":
    main()
