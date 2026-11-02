@echo off
echo ====================================================
echo  Running AutoApply AI Test Suite (pytest)
echo ====================================================

call .venv\Scripts\activate.bat
set PYTHONPATH=autoapply-ai\backend
pytest autoapply-ai\backend\tests -v
pause

