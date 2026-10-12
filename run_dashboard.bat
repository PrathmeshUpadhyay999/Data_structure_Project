@echo off
cd /d "%~dp0"
title Heatwave Intelligence Dashboard
echo Starting Heatwave Intelligence dashboard...
echo Keep this window open while using the dashboard.
echo Open http://127.0.0.1:5051 in your browser.
echo.
python -m heatwave_dashboard.server --port 5051
if errorlevel 1 (
    echo.
    echo The dashboard stopped or could not start. Check the message above.
    pause
)
