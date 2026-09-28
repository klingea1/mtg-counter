@echo off
REM Double-click to build MTG-Counter-Windows.zip (app + bundled Python).
REM
REM This just runs make-bundle.ps1. The ExecutionPolicy flag is here because
REM Windows blocks double-clicked PowerShell scripts by default; it applies to
REM this one run only and changes nothing on the machine.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0make-bundle.ps1"
pause
