"""smoke_agent_web.py - 30 秒全路由烟测。

用法：
    python tools/smoke_agent_web.py [host:port]
        默认 http://127.0.0.1:8765

读 .agent_web.token（启动时打印），从 token= 头撞每个端点；不依赖 pytest。
所有检查都非破坏性（只 GET / POST /api/chat 发无害 status）。
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOKEN_FILE = ROOT / ".agent_web.token"


def _read_token() -> str | None:
    if not TOKEN_FILE.is_file():
        return None
    try:
        return TOKEN_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return None


def _req(url: str, method: str = "GET", body: dict | None = None,
         token: str | None = None, timeout: int = 8) -> tuple[int, dict]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["X-DSH-Token"] = token
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = r.read()
            try:
                return r.status, json.loads(payload.decode("utf-8", "replace"))
            except Exception:
                return r.status, {"raw": payload[:200].decode("utf-8", "replace")}
    except urllib.error.HTTPError as e:
        return e.code, {"err": str(e)}
    except Exception as e:
        return 0, {"err": repr(e)}


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
    token = _read_token()
    print(f"smoke → {base}  token={'<set>' if token else '<missing>'}")

    cases_pass = cases_fail = 0

    def check(name: str, ok, detail: str = ""):
        nonlocal cases_pass, cases_fail
        marker = "  ok" if ok else "  FAIL"
        cases_pass += int(bool(ok))
        cases_fail += int(not bool(ok))
        print(f"{marker:8s} {name}  {detail}")

    # 1. ping
    code, body = _req(f"{base}/api/ping")
    check("ping 200", code == 200 and body.get("ok") is True, f"({code})")

    # 2. 无 token → 数据路由全 403
    for path in ["/api/cases", "/api/state", "/api/views", "/api/actions", "/api/jobs"]:
        code, _ = _req(f"{base}{path}")
        check(f"无 token {path} → 403", code == 403, f"({code})")

    if not token:
        print("\n  ! 没找到 .agent_web.token，跳过鉴权后用例。")
        print(f"  失败 {cases_fail} / 通过 {cases_pass}")
        return 1 if cases_fail else 0

    # 3. cases
    code, body = _req(f"{base}/api/cases", token=token)
    case_list = (body or {}).get("cases", []) if isinstance(body, dict) else []
    check("cases 200 + ≥1 案例", code == 200 and len(case_list) >= 1,
          f"({code}, {len(case_list)} cases)")

    if not case_list:
        print(f"  失败 {cases_fail} / 通过 {cases_pass}")
        return 1

    cid = case_list[0]["id"]
    print(f"  用 {cid} 跑后续")

    # 4. state
    code, body = _req(f"{base}/api/state?case={cid}", token=token)
    check("state 200 + case_id", code == 200 and body.get("case_id") == cid,
          f"({code})")

    # 5. views
    code, body = _req(f"{base}/api/views?case={cid}", token=token)
    has_groups = isinstance(body, dict) and isinstance(body.get("groups"), list) \
                 and any(isinstance(g.get("views"), list) for g in body.get("groups", []))
    check("views 200 + 有 groups", code == 200 and has_groups, f"({code})")

    # 6. chat GET
    code, body = _req(f"{base}/api/chat?case={cid}", token=token)
    check("chat GET 200", code == 200, f"({code})")

    # 7. chat POST status / pending / next / find
    for msg in ["status", "pending", "next", "find requirements", "help"]:
        code, body = _req(f"{base}/api/chat", method="POST",
                          body={"text": msg, "case": cid}, token=token)
        reply = (body or {}).get("reply", "") if isinstance(body, dict) else ""
        check(f"chat '{msg}' 200", code == 200 and len(reply) > 0,
              f"({code}, {len(reply)} chars)")

    # 8. actions
    code, body = _req(f"{base}/api/actions", token=token)
    check("actions 200", code == 200, f"({code})")

    # 9. 未知 case 静默回退到 default（不报错）
    code, body = _req(f"{base}/api/state?case=NOPE_NOT_EXIST", token=token)
    check("未知 case 回退 default", bool(code == 200 and body.get("case_id")),
          f"({code}, fallback={body.get('case_id')})")

    # 10. 错误 token → 403
    code, _ = _req(f"{base}/api/cases", token="WRONG_TOKEN_123")
    check("错 token → 403", code == 403, f"({code})")

    print(f"\n  通过 {cases_pass} / 失败 {cases_fail}")
    return 0 if cases_fail == 0 else 1


if __name__ == "__main__":
    t0 = time.time()
    rc = main()
    print(f"  用时 {time.time() - t0:.2f}s")
    sys.exit(rc)
