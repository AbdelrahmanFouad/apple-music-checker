@echo off
title Apple Music Live Checker ^& CD Tracker Sync
cd /d "%~dp0"

set PYTHONUNBUFFERED=1
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

set "PY="
if exist "%USERPROFILE%\.venv\Scripts\python.exe" set "PY=%USERPROFILE%\.venv\Scripts\python.exe"
if not defined PY if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
if not defined PY set "PY=python"

echo ========================================================
echo Starting Apple Music Live Checker on http://localhost:8502
echo ========================================================
"%PY%" -m streamlit run streamlit_app.py --server.port 8502 --server.headless false
pause
