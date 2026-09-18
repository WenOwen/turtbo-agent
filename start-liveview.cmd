@echo off
setlocal
title 叶轮机械设计工作台 - 实时窗口

set "ROOT=%~dp0"
cd /d "%ROOT%"

echo ============================================================
echo   叶轮机械设计工作台 - 实时窗口
echo ============================================================
echo.
echo   正在启动本地服务，浏览器会自动打开。
echo   关闭这个窗口即停止服务。
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 找不到 python。请确认已安装 Python 3.10+ 并加入 PATH。
    pause
    exit /b 1
)

set PYTHONIOENCODING=utf-8
python tools\liveview.py %*

if errorlevel 1 (
    echo.
    echo [错误] 服务异常退出。
    pause
)
endlocal
