@echo off
rem Starts Garmin Lifetime Analyzer without Docker. Double-click it, or run: start.cmd -Update
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
if errorlevel 1 pause
