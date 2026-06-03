@echo off
set DIR=%~dp0
if not exist "%DIR%.venv" (
    python "%DIR%bootstrap.py"
    if errorlevel 1 exit /b 1
)
python "%DIR%run_dev.py"

