"""job_state.py - 进程内共享的后台任务状态（agent_web 写，agent_reply 读）。
无依赖。线程安全。
"""
from __future__ import annotations

import secrets
import threading
import datetime as _dt
from typing import Any, Dict, Optional

_JOBS_LOCK = threading.Lock()
_JOBS: Dict[str, Dict[str, Any]] = {}


def now_iso() -> str:
    return _dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


def start_job(case_id: str, label: str, command: str) -> str:
    """登记一个新任务，状态=running，返回 job_id。"""
    job_id = secrets.token_urlsafe(8)
    with _JOBS_LOCK:
        # 控 jobs 表大小
        if len(_JOBS) > 50:
            oldest = sorted(_JOBS.items(),
                            key=lambda kv: kv[1].get("started") or "")[:10]
            for jid in dict(oldest):
                _JOBS.pop(jid, None)
        _JOBS[job_id] = {
            "job_id": job_id,
            "case": case_id,
            "label": label,
            "command": command,
            "status": "running",
            "started": now_iso(),
            "finished": None,
            "exit": None,
            "stdout_tail": "",
            "stderr_tail": "",
            "ok": None,
        }
    return job_id


def update_job(job_id: str, **fields: Any) -> None:
    with _JOBS_LOCK:
        rec = _JOBS.get(job_id)
        if rec is not None:
            rec.update(fields)


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _JOBS_LOCK:
        rec = _JOBS.get(job_id)
        return dict(rec) if rec else None


def list_jobs(case: Optional[str] = None, limit: int = 30) -> list:
    with _JOBS_LOCK:
        rows = list(_JOBS.values())
    if case:
        rows = [r for r in rows if r.get("case") == case]
    rows.sort(key=lambda r: r.get("started") or "", reverse=True)
    return rows[:limit]
