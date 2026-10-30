"""生成两个账号的最终资料：头像（512/200）+ 一张可照抄的资料表。

产物：output/账号资料/
    账号1-老韩读报.md / 账号2-档案室.md
    头像-账号1-512.png / 头像-账号1-200.png / 账号2 同
"""
import shutil
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(r"D:\AIdianshangzongheti")
OUT = ROOT / "output" / "账号资料"
OUT.mkdir(parents=True, exist_ok=True)

FFMPEG = shutil.which("ffmpeg") or r"C:\Users\morel\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe"

ACCOUNTS = [
    {
        "no": "账号1",
        "persona": "N1-老韩读报",
        "avatar": ROOT / "output" / "人设-新闻" / "N1-老韩读报" / "avatar-n1.png",
        "name": "老韩读报",
        "alt_names": ["老韩读报", "老韩讲时事", "读报的老韩"],
        "one_line": "把外面的事读给你听，顺便说说跟你有什么关系。",
        "bio_short": "读外媒和公报，只讲查得到出处的事。",
        "bio_long": "读外媒和公报，只讲查得到出处的事；说不清的就说说不清。国际时事与政策解读，讲清楚发生了什么、跟你有什么关系。",
        "domain": "资讯 / 国际",
        "tags": "国际观察、政策解读、时事",
        "content": "国际与军事观察（只讲公开信息）+ 每周两期政策解读",
    },
    {
        "no": "账号2",
        "persona": "N4-档案室",
        "avatar": ROOT / "output" / "人设-新闻" / "N4-档案室" / "avatar-n4.png",
        "name": "档案室",
        "alt_names": ["档案室", "旧档房", "翻档案的人"],
        "one_line": "翻旧文件，讲被忘掉的那部分。",
        "bio_short": "翻旧文件、老照片，讲被忘掉的那部分历史。",
        "bio_long": "翻旧文件、老照片、地方志，讲被忘掉的那部分历史。只写查得到的细节，查不到的就不写。",
        "domain": "历史",
        "tags": "近代史、档案、冷知识",
        "content": "近代史与战史、工业建设史",
    },
]


def shrink(src: Path, size: int, dst: Path) -> None:
    subprocess.run(
        [FFMPEG, "-y", "-loglevel", "error", "-i", str(src),
         "-vf", f"scale={size}:{size}:flags=lanczos", str(dst)],
        check=True,
    )


def main() -> None:
    for acc in ACCOUNTS:
        if not acc["avatar"].is_file():
            raise SystemExit(f"头像不存在：{acc['avatar']}")

        big = OUT / f"头像-{acc['no']}-512.png"
        small = OUT / f"头像-{acc['no']}-200.png"
        shrink(acc["avatar"], 512, big)
        shrink(acc["avatar"], 200, small)

        card = f"""# {acc['no']} · {acc['name']}

> 照这张表填头条号后台，一次填完。

## 1. 头像

| 用途 | 文件 |
|---|---|
| 上传用（512×512） | `{big}` |
| 备用（200×200） | `{small}` |
| 原图（1024×1024） | `{acc['avatar']}` |

## 2. 昵称

**首选**：{acc['name']}

备选：{'、'.join(acc['alt_names'][1:])}

> 昵称改一次有成本，想好再存。建议就用首选。

## 3. 简介（头条号签名）

**短版（推荐，一行不折行）**
```
{acc['bio_short']}
```

**长版（放得下就用这个）**
```
{acc['bio_long']}
```

## 4. 领域 / 分类

**{acc['domain']}**

## 5. 标签

{acc['tags']}

## 6. 这个号发什么

{acc['content']}

## 7. 一句话定位

{acc['one_line']}

## 8. 人设卡（写作时用）

`output/人设-新闻/{acc['persona']}/人设卡.md`

在写作台「人设」下拉里选 **{acc['name']}**，生成时就会按这个身份写。
"""
        (OUT / f"{acc['no']}-{acc['name']}.md").write_text(card, encoding="utf-8")
        print(f"[完成] {acc['no']} {acc['name']} → {big.name} / {small.name}")

    print("\n资料表：", OUT)


if __name__ == "__main__":
    main()
