@echo off
cd /d "%~dp0"
if not exist .venv (
  py -m venv .venv
)
call .\.venv\Scripts\activate
pip install -r requirements.txt
set PORT=5050
python -u app.py
pause
