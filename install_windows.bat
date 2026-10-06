@echo off
setlocal
cd /d %~dp0
where py >nul 2>nul
if errorlevel 1 (
  echo Python 3.11 ou 3.12 est requis. Installez-le depuis python.org puis relancez ce fichier.
  pause
  exit /b 1
)
py -3.11 -m venv .venv 2>nul || py -3.12 -m venv .venv
if errorlevel 1 (
  echo Impossible de creer l'environnement Python. Verifiez votre installation Python.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
  echo L'installation a echoue. Verifiez votre connexion Internet puis relancez.
  pause
  exit /b 1
)
echo.
echo HENO est installe. Lancez run_windows.bat.
pause
