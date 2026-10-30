"""比较两份头条登录态里的身份 cookie，判断是不是同一个账号。

头条的身份 cookie：
  uid_tt / uid_tt_ss —— 编码了账号 ID
  sid_tt / sessionid —— 每次登录都不同，同一账号也会不同，不能用来判断身份
"""
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

STATE = r"D:\AIdianshangzongheti\output\_state"
FILES = {
    "main（号1，已确认登录）": rf"{STATE}\toutiao-main.json",
    "second（刚扫的那个）": rf"{STATE}\toutiao-second.same-as-main.json.bak",
    "second（更早的假状态）": rf"{STATE}\toutiao-second.fake-20261030.json.bak",
}

KEYS = ("uid_tt", "uid_tt_ss", "sid_tt", "sid_guard", "sessionid", "sessionid_ss")


def load(path):
    data = json.load(open(path, encoding="utf-8"))
    return {c["name"]: c["value"] for c in data.get("cookies", [])}


cookies = {}
for label, path in FILES.items():
    try:
        cookies[label] = load(path)
    except FileNotFoundError:
        print(f"{label}: 文件不存在")

for key in KEYS:
    print(f"\n[{key}]")
    for label, cs in cookies.items():
        val = cs.get(key, "（没有）")
        print(f"  {label:26s} {val[:40]}")
