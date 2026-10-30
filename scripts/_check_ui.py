import sys

sys.stdout.reconfigure(encoding="utf-8")
t = open(r"D:\AIdianshangzongheti\pipeline\gui\ui.html", encoding="utf-8").read()
print("w-extra:", t.count('id="w-extra"'))
print("w-acc 残留:", "w-acc" in t)
print("accountsFor 已加:", "function accountsFor" in t)
print("accSelect 已加:", "function accSelect" in t)
print("data-acc-for:", t.count("data-acc-for"))
