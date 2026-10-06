@echo off
setlocal
cd /d %~dp0
if not exist .venv\Scripts\python.exe call install_windows.bat
call .venv\Scripts\activate.bat
pyinstaller HENO.spec --noconfirm --clean
if errorlevel 1 exit /b 1
echo Build termine dans dist\HENO-Meeting-Assistant\
pause
