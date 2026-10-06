@echo off
cd /d %~dp0
if not exist .venv\Scripts\python.exe (
  echo HENO n'est pas encore installe. Lancez install_windows.bat d'abord.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python app.py
