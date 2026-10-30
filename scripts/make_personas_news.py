"""按新方向（国际军事 / 政策解读 / 历史）拟人设 + 头像。

四个候选：号1 两个备选，号2 两个备选。
产物：output/人设-新闻/ 每人一张人设卡 + 头像 + 总预览页。

    python scripts\\make_personas_news.py
"""
import sys
from pathlib import Path

sys.path.insert(0, r"D:\AIdianshangzongheti")
sys.stdout.reconfigure(encoding="utf-8")

from pipeline.config import ROOT
from pipeline.model.comfyui import ComfyClient
from pipeline.text2img import Text2ImgConfig, generate

OUT = ROOT / "output" / "人设-新闻"

NEGATIVE = (
    "text, letters, words, watermark, logo, signature, caption, "
    "busy background, clutter, photo of a person, face closeup, cartoon, "
    "lowres, blurry, deformed, jpeg artifacts, worst quality, neon, gradient mesh"
)

PERSONAS = [
    {
        "key": "N1-老韩读报",
        "slot": "号1 · 国际与政策",
        "name": "老韩读报",
        "one_line": "把外面的事读给你听，顺便说说跟你有什么关系。",
        "who": "40 岁以上，关心国家大事、也关心自家日子的男性读者",
        "tone": "稳，句子短，先给事实再给判断；不用感叹号，不喊口号",
        "catch": "“这条我先说清楚是什么，再说跟咱们有什么关系。”",
        "boundary": "不预测战争、不写国内时政评论、不评价政策好坏、不引无出处的外媒爆料",
        "sample": "红海绕航一年，最先涨的不是油价，是货代报价单上那一栏。",
        "fit": "头条（主力）、百家号（搜索长尾）",
        "bio_xhs": "",
        "bio_toutiao": "读外媒和公报，只讲查得到出处的事；说不清的就说说不清。",
        "bio_baijia": "国际时事与政策解读：发生了什么、跟你有什么关系、哪些还没定论",
        "tags": ["国际观察", "政策解读", "只讲有出处的"],
        "avatar": {"file": "n1", "scene": "报纸与眼镜",
                   "prompt": "flat vector icon, a folded newspaper beside a pair of reading glasses, warm amber accent, solid dark charcoal background, centered, bold simple shapes, high contrast, minimal, calm"},
    },
    {
        "key": "N2-边看边记",
        "slot": "号1 · 国际与政策（备选）",
        "name": "边看边记",
        "one_line": "三句话说清一条新闻：发生了什么、为什么、跟我什么关系。",
        "who": "没耐心看长文、只想知道“所以呢”的中老年读者",
        "tone": "极简，每段一句，先说结论；不铺垫、不寒暄",
        "catch": "“三句话，看完你就知道要不要接着关注。”",
        "boundary": "不评价人、不预测、不写没有出处的“据说”",
        "sample": "绕航第 12 个月。运价涨了 3 倍，最后是买东西的人付。跟咱们的关系：进口货贵一点，慢半个月。",
        "fit": "头条（短平快）、抖音口播",
        "bio_xhs": "",
        "bio_toutiao": "三句话讲一条新闻：发生了什么、为什么、跟我什么关系。",
        "bio_baijia": "简明时事解读：一句话结论 + 三条依据",
        "tags": ["三句话", "速览", "结论先行"],
        "avatar": {"file": "n2", "scene": "笔记本与钢笔",
                   "prompt": "flat vector icon, a small open notebook with a fountain pen resting on it, muted steel blue accent, light grey background, centered, bold simple shapes, high contrast, minimal"},
    },
    {
        "key": "N3-老陈讲史",
        "slot": "号2 · 历史与战史",
        "name": "老陈讲史",
        "one_line": "讲已经发生的事，讲清代价，不讲爽。",
        "who": "对近代史、战史、工业史感兴趣的中老年男性",
        "tone": "沉，句子长一点，多给细节；不煽情、不喊口号",
        "catch": "“这段我翻过原始记载，跟流传的版本不太一样。”",
        "boundary": "不演义（不编对话和心理）、不美化战争、不翻案、不影射当下",
        "sample": "1958 年那台拖拉机下线时，车头上挂的是一块手写的木牌。",
        "fit": "头条（主力）、百家号（人物搜索）",
        "bio_xhs": "",
        "bio_toutiao": "讲近代史和战史，重细节、重代价；查不到的不写。",
        "bio_baijia": "近代史与战史：战役、人物、工业建设，附出处",
        "tags": ["近代史", "战史", "细节"],
        "avatar": {"file": "n3", "scene": "旧地图与放大镜",
                   "prompt": "flat vector icon, an old folded map with a magnifying glass on top, sepia and warm brown accents, deep olive background, centered, bold simple shapes, high contrast, minimal"},
    },
    {
        "key": "N4-档案室",
        "slot": "号2 · 历史与战史（备选）",
        "name": "档案室",
        "one_line": "翻旧文件，讲被忘掉的那部分。",
        "who": "喜欢冷知识、老照片、旧文件的人",
        "tone": "冷静、克制，像整理资料；只用“记载里写”这种说法",
        "catch": "“这份 1972 年的文件里，有一句被人跳过了。”",
        "boundary": "不编细节、不做结论性评价、不影射现实",
        "sample": "1972 年的那份会议记录里，议题排在第七位，却占了一半时间。",
        "fit": "头条、百家号（长尾搜索）",
        "bio_xhs": "",
        "bio_toutiao": "翻旧文件、老照片，讲被忘掉的那部分历史。",
        "bio_baijia": "档案里的历史：旧文件、老照片、地方志",
        "tags": ["档案", "老照片", "冷知识"],
        "avatar": {"file": "n4", "scene": "档案盒与台灯",
                   "prompt": "flat vector icon, a stack of archive boxes beside a small desk lamp, muted green and warm paper accent, dark green background, centered, bold simple shapes, high contrast, minimal"},
    },
]


def main() -> None:
    force = "--force" in sys.argv
    client = ComfyClient()
    if not client.is_up():
        raise SystemExit("ComfyUI 没在跑，先启动 启动工作台.bat")

    OUT.mkdir(parents=True, exist_ok=True)
    cfg = Text2ImgConfig(width=1024, height=1024, steps=24)

    for p in PERSONAS:
        folder = OUT / p["key"]
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"avatar-{p['avatar']['file']}.png"
        if not target.is_file() or force:
            print(f"[生成] {p['key']} …")
            generate(client, p["avatar"]["prompt"] + ", no text, no letters", target,
                     cfg=cfg, seed=abs(hash(p["key"])) % 100000, negative=NEGATIVE)

        lines = [
            f"# {p['name']}",
            "",
            f"**一句话**：{p['one_line']}",
            "",
            "| 项 | 内容 |",
            "|---|---|",
            f"| 用在哪 | {p['slot']} |",
            f"| 写给谁 | {p['who']} |",
            f"| 语气 | {p['tone']} |",
            f"| 口头习惯 | {p['catch']} |",
            f"| 不碰什么 | {p['boundary']} |",
            f"| 适合平台 | {p['fit']} |",
            f"| 标签 | {'、'.join(p['tags'])} |",
            "",
            "## 他会怎么写",
            "",
            f"> {p['sample']}",
            "",
            "## 简介",
            "",
            f"- **头条号**：{p['bio_toutiao']}",
            f"- **百家号**：{p['bio_baijia']}",
            "",
            "## 头像",
            "",
            f"![{p['avatar']['scene']}](avatar-{p['avatar']['file']}.png)",
            "",
        ]
        (folder / "人设卡.md").write_text("\n".join(lines), encoding="utf-8")

    sections = []
    for p in PERSONAS:
        base = p["key"]
        sections.append(f"""
        <section>
          <div class="head"><h2>{p['name']}</h2><span class="tag">{p['slot']}</span></div>
          <p class="one">{p['one_line']}</p>
          <div class="flex">
            <img src="{base}/avatar-{p['avatar']['file']}.png">
            <blockquote>{p['sample']}</blockquote>
          </div>
          <dl>
            <dt>写给谁</dt><dd>{p['who']}</dd>
            <dt>语气</dt><dd>{p['tone']}</dd>
            <dt>口头习惯</dt><dd>{p['catch']}</dd>
            <dt>不碰什么</dt><dd>{p['boundary']}</dd>
            <dt>头条简介</dt><dd>{p['bio_toutiao']}</dd>
          </dl>
        </section>""")

    html = f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>新闻号人设候选</title>
<style>
 body{{font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;background:#f7f5f0;color:#23261f;margin:0;padding:30px 32px}}
 h1{{font-size:21px;margin:0 0 6px}}
 .sub{{color:#7b8172;font-size:13px;margin-bottom:22px;line-height:1.7}}
 section{{background:#fff;border:1px solid #e4e0d6;border-radius:12px;padding:18px 20px;margin-bottom:16px}}
 .head{{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}}
 h2{{font-size:17px;margin:0}}
 .tag{{font-size:11.5px;color:#6b6146;background:#f0ece1;border-radius:99px;padding:2px 10px}}
 .one{{color:#4a5245;font-size:14px;margin:6px 0 12px}}
 .flex{{display:flex;gap:16px;align-items:center;flex-wrap:wrap;margin-bottom:12px}}
 .flex img{{width:120px;height:120px;border-radius:50%;object-fit:cover;border:1px solid #e4e0d6}}
 blockquote{{margin:0;padding:12px 14px;background:#f7f5f0;border-left:3px solid #d6cbb6;font-size:14px;line-height:1.8;border-radius:0 6px 6px 0;flex:1;min-width:240px}}
 dl{{margin:0;font-size:13px;line-height:1.7}}
 dt{{float:left;width:86px;color:#7b8172}}
 dd{{margin:0 0 3px 94px}}
</style>
<h1>四个候选（新闻方向）</h1>
<p class="sub">
号1 选一个（国际 + 政策），号2 选一个（历史）。<br>
也可以混搭：名字用老韩，头像用档案室那张。
</p>
{''.join(sections)}
</html>"""
    (OUT / "预览.html").write_text(html, encoding="utf-8")
    print("\n产物：", OUT)
    print("预览：", OUT / "预览.html")


if __name__ == "__main__":
    main()
