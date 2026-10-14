"""test_smoke.py - 跑一次烟测（不依赖服务，用 stub server）。"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SMOKE = ROOT / "tools" / "smoke_agent_web.py"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _wait_ready(url: str, timeout: float = 8.0) -> bool:
    import urllib.request
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(url, timeout=1) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.2)
    return False


def test_smoke_runs_against_real_server(tmp_path):
    """起真服务 + 跑 smoke，应全部通过。"""
    port = _free_port()
    log = tmp_path / "srv.log"
    # 用 Popen 的 DEVNULL stdout，避免乱码进 log 文件
    proc = subprocess.Popen(
        [sys.executable, "-c",
         "from tools.agent_web import main; main(['--port', str(%d), '--no-browser'])" % port],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        if not _wait_ready(f"http://127.0.0.1:{port}/api/ping"):
            raise RuntimeError("server didn't come up")
        # 等服务把 token 写进 .agent_web.token
        for _ in range(50):
            if (ROOT / ".agent_web.token").is_file():
                break
            time.sleep(0.1)
        rc = subprocess.call(
            [sys.executable, str(SMOKE), f"http://127.0.0.1:{port}"],
            cwd=str(ROOT),
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        assert rc == 0, f"smoke exit={rc}"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        # 清理 token 文件
        try:
            (ROOT / ".agent_web.token").unlink()
        except Exception:
            pass
