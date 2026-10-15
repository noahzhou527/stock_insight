@echo off
chcp 65001 >nul
cd /d "%~dp0..\stock_insight_public_backup_20261010"
if not exist "app.py" (
    echo Public version backup not found.
    exit /b 1
)
echo Public version: http://localhost:8502
"%~dp0.venv\Scripts\python.exe" -m streamlit run app.py --server.port 8502 --server.address 127.0.0.1
