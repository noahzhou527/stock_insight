@echo off
cd /d "%~dp0"
git switch codex/ifind
if errorlevel 1 exit /b 1
call "%~dp0start.bat"
