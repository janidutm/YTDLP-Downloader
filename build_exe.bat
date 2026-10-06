@echo off
setlocal
cd /d "%~dp0"
py -3.11 -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements-build.txt
python -m PyInstaller --noconfirm --clean --windowed --collect-all ttkbootstrap --collect-all PIL --name YouTubeDownloader app.py
echo.
echo Build complete. See dist\YouTubeDownloader\
pause
