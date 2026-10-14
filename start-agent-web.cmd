@echo off
REM Start the three-panel agent web UI
REM   - 默认监听 127.0.0.1:8765
REM   - token 写在 .agent_web.token（启动时自动生成并打印）
REM   - 关闭后保留 token，便于书签/防火墙复用
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    python -m uvicorn tools.agent_web:app --host 127.0.0.1 --port 8765
) else (
    .venv\Scripts\python -m uvicorn tools.agent_web:app --host 127.0.0.1 --port 8765
)
endlocal
