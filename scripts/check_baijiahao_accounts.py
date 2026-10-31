"""核对两个百家号账号是不是不同的人（用后台 appinfo 的 id 判断）。

    ... python scripts/check_baijiahao_accounts.py
"""
import sys

sys.path.insert(0, r"D:\AIdianshangzongheti")
sys.stdout.reconfigure(encoding="utf-8")

import pipeline.content.baijiahao as bjh

fields = []
for account in ("main", "second"):
    info = bjh.identity(account)
    if not info:
        print(f"{account}: 没有登录态文件 {bjh.state_file(account)}")
        continue
    print(f"{account}: id={info.get('id') or '（读不到）'}  name={info.get('name') or '（读不到）'}")
    fields.append(info)

ids = [f.get("id") for f in fields if f.get("id")]
print()
if len(ids) < 2:
    print("⚠ 只读到 %d 个账号，没法比对" % len(ids))
elif len(set(ids)) != len(ids):
    print("⚠ 两个账号是同一个百家号 —— 必须换号重新登录")
else:
    print("✅ 两个账号是独立的百家号")
