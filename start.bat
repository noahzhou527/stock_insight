@echo off
rem Stock Insight launcher (docs/plan-b-draft.md section 7):
rem   1. make sure .venv exists and backend\requirements.txt is installed
rem   2. build frontend\dist if missing (needs Node.js)
rem   3. first run only: import the legacy data\cache into the SQLite database
rem   4. start the backend on 127.0.0.1 and open the browser
rem Optional environment variables: STOCK_INSIGHT_PORT (default 8000), STOCK_INSIGHT_NO_BROWSER=1
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not defined STOCK_INSIGHT_PORT set "STOCK_INSIGHT_PORT=8000"
set "URL=http://127.0.0.1:%STOCK_INSIGHT_PORT%"
set "PY=.venv\Scripts\python.exe"
rem Python output in UTF-8 too, so it matches chcp 65001 when the window output is redirected to a log
set "PYTHONIOENCODING=utf-8"

rem ---------------------------------------------------------------- Python
if exist "%PY%" goto venv_ready
where python >nul 2>&1
if errorlevel 1 (
    echo [Stock Insight] 没有找到 Python。请安装 Python 3.11 或更高版本，并勾选 "Add python.exe to PATH"。
    goto fail
)
python -c "import sys; sys.exit(sys.version_info < (3, 11))"
if errorlevel 1 (
    echo [Stock Insight] Python 版本过低，需要 3.11 或更高版本。
    goto fail
)
echo [Stock Insight] 首次运行：正在创建虚拟环境 .venv ...
python -m venv .venv
if errorlevel 1 (
    echo [Stock Insight] 创建虚拟环境失败。
    goto fail
)
:venv_ready

rem Reinstall only when backend\requirements.txt changed since the last successful install.
fc /b backend\requirements.txt .venv\requirements.installed >nul 2>&1
if not errorlevel 1 goto deps_ready
echo [Stock Insight] 正在安装后端依赖（首次需要几分钟）...
"%PY%" -m pip install --disable-pip-version-check -q -r backend\requirements.txt
if errorlevel 1 (
    echo [Stock Insight] 安装后端依赖失败，请检查网络后重试。
    goto fail
)
copy /y backend\requirements.txt .venv\requirements.installed >nul
:deps_ready

rem ---------------------------------------------------------------- frontend
if exist "frontend\dist\index.html" goto dist_ready
where npm >nul 2>&1
if errorlevel 1 (
    echo [Stock Insight] 前端尚未构建，构建需要 Node.js 20 或更高版本：https://nodejs.org/
    echo                 安装后重新运行 start.bat；或者在别处构建好后把 frontend\dist 复制过来。
    goto fail
)
echo [Stock Insight] 正在构建前端（首次需要一两分钟）...
pushd frontend
call npm ci --no-audit --no-fund
if errorlevel 1 (
    popd
    echo [Stock Insight] 安装前端依赖失败。
    goto fail
)
call npm run build
if errorlevel 1 (
    popd
    echo [Stock Insight] 前端构建失败。
    goto fail
)
popd
:dist_ready

rem ---------------------------------------------------------------- database
rem Schema migrations and the built-in stock pool are applied by the backend on every start.
rem The legacy cache import runs once, before the database file exists.
if exist "data\stock_insight.db" goto db_ready
echo [Stock Insight] 首次运行：导入旧版 data\cache 中的日线与自选（只读，不会删除任何文件）...
"%PY%" -m backend.scripts.migrate_legacy_cache
:db_ready

rem ---------------------------------------------------------------- run
netstat -ano | findstr /r /c:":%STOCK_INSIGHT_PORT% .*LISTENING" >nul
if not errorlevel 1 (
    echo [Stock Insight] 端口 %STOCK_INSIGHT_PORT% 已被占用，可能已经在运行。直接打开 %URL%
    echo                 如需换端口：set STOCK_INSIGHT_PORT=8001 后再运行 start.bat
    if not "%STOCK_INSIGHT_NO_BROWSER%"=="1" start "" "%URL%"
    goto end
)
echo [Stock Insight] %URL%   （关闭此窗口即停止服务）
if not "%STOCK_INSIGHT_NO_BROWSER%"=="1" start "" cmd /c "timeout /t 3 /nobreak >nul && start %URL%"
"%PY%" -m uvicorn backend.app.main:app --host 127.0.0.1 --port %STOCK_INSIGHT_PORT%
goto end

:fail
pause
exit /b 1

:end
endlocal
