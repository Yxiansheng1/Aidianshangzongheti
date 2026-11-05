"""L1 收货抽查：工具注册表 + API 是否真的能对接。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.harness.policy import Autonomy, AutonomyController, Risk
from pipeline.harness.agent import _interrupt_on


def main() -> None:
    from pipeline.tools import build_registry

    reg = build_registry()
    print("工具清单：")
    for item in reg.describe():
        print(f"  · {item['name']:16s} {item['risk']:12s} critical={item['critical']}")

    print("\n三档闸门（真实注册表）：")
    for level in (Autonomy.AUTO, Autonomy.STANDARD, Autonomy.STEP):
        mapping = _interrupt_on(reg, AutonomyController(level))
        need = [k for k, v in mapping.items() if v]
        print(f"  {level.value:9s} 停：{', '.join(need) if need else '（不停）'}")

    print("\n风险等级自洽性：")
    bad = [s.name for s in reg.all() if s.risk is Risk.IRREVERSIBLE and s.name != "publish"]
    print("  不可逆工具：", [s.name for s in reg.all() if s.risk is Risk.IRREVERSIBLE])
    print("  异常不可逆：", bad or "无")

    print("\nAPI 冒烟：")
    from fastapi.testclient import TestClient

    from pipeline.api.app import app

    client = TestClient(app)
    r = client.get("/api/health")
    print("  /api/health:", r.status_code, str(r.json())[:120])
    r2 = client.get("/api/tools")
    body = r2.json()
    n = len(body.get("tools", body if isinstance(body, list) else []))
    print("  /api/tools:", r2.status_code, f"工具数={n}")


if __name__ == "__main__":
    main()
