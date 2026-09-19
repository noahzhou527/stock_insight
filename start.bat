@echo off
rem Stock Insight 一键启动：使用项目自带虚拟环境，固定运行在 8501 端口。
rem 双击运行，或在任意终端中执行本脚本均可，无需手动激活虚拟环境。
chcp 65001 >nul
cd /d "%~dp0"

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

echo [Stock Insight] 正在启动，浏览器将自动打开 http://localhost:8501
start "" cmd /c "timeout /t 4 /nobreak >nul && start http://localhost:8501"
".venv\Scripts\python.exe" -m streamlit run app.py --server.port 8501
