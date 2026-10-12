@echo off
cd /d "%~dp0"
title Heatwave AWS Live Simulator
echo Starting the simulated AWS data stream...
echo This writes readings to the project's SQLite database.
echo Keep the dashboard running separately on http://127.0.0.1:5051.
echo Press Ctrl+C to stop the stream.
echo.
python main.py simulate-aws --live --tick-seconds 2.0
if errorlevel 1 (
    echo.
    echo The AWS simulator stopped or could not start. Check the message above.
    pause
)
