@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Read the launch body before switching, since the target branch owns this file too.
(
    git switch codex/ifind
    if errorlevel 1 (
        echo [Stock Insight] Cannot switch versions. Resolve local changes and try again.
        pause
        exit /b 1
    )
if not exist ".venv\Scripts\python.exe" (
    echo [Stock Insight] 未找到虚拟环境，正在创建并安装依赖（首次运行需要几分钟）...
    python -m venv .venv
    if errorlevel 1 (
        echo [Stock Insight] 创建虚拟环境失败，请确认已安装 Python 3.10+ 并加入 PATH。
        pause
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)
    echo [Stock Insight] ifind: http://localhost:8501
    start "" cmd /c "timeout /t 4 /nobreak >nul && start http://localhost:8501"
    ".venv\Scripts\python.exe" -m streamlit run app.py --server.port 8501 --server.address 127.0.0.1
)
