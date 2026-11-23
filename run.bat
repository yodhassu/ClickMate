@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\activate.bat" (
    echo First run: creating virtual environment...
    py -3 -m venv .venv
    call ".venv\Scripts\activate.bat"
    pip install -r requirements.txt
) else (
    call ".venv\Scripts\activate.bat"
)
python app.py
pause
