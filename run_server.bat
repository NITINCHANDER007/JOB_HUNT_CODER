@echo off
echo ====================================================
echo  Starting AutoApply AI (Native Windows Server)
echo ====================================================

if not exist ".venv\Scripts\python.exe" (
    echo Creating Python virtual environment in .venv...
    python -m venv --system-site-packages .venv
)

echo Activating virtual environment...
call .venv\Scripts\activate.bat

echo Starting server on http://localhost:5050...
python autoapply-ai\backend\run.py
pause
