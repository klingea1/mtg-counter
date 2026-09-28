@echo off
REM Double-click this file to start the MTG Counter server on Windows.
cd /d "%~dp0"

set "PY="

REM 1. The bundled runtime, if this came from the ready-to-run download.
if exist "%~dp0python\python.exe" set "PY=%~dp0python\python.exe"

REM 2. Otherwise a Python already installed on this machine.
REM
REM    Checking PATH alone is NOT enough here, and getting this wrong is what
REM    broke this file once already. Windows ships a stub called python.exe
REM    (an "App execution alias") that sits on PATH even when Python is not
REM    installed. Run it and it only prints "Python was not found" and points
REM    at the Microsoft Store. `where python` finds that stub and reports
REM    success, so a PATH check says yes and then nothing works, and the
REM    person never sees the message below. So each candidate is actually run
REM    and has to report a real version number before we believe it.
if not defined PY call :probe py
if not defined PY call :probe python
if not defined PY call :probe python3

if defined PY (
    "%PY%" server.py %*
    goto :end
)

echo.
echo Could not start: no working Python was found.
echo.
echo If you downloaded the ready-to-run version, there should be a folder
echo called "python" sitting right next to this file. There isn't one, which
echo almost always means the zip was opened instead of extracted. Windows
echo lets you look inside a zip without unpacking it, and nothing will run
echo from in there.
echo.
echo   Right-click the zip, choose "Extract All", open the extracted
echo   folder, and double-click this file again.
echo.
echo If you meant to use a Python of your own instead: install it from the
echo Microsoft Store, or from https://www.python.org/downloads/ ^(and tick
echo "Add python.exe to PATH" during setup^). Then run this file again.
echo.
goto :end

:probe
REM Does the name exist at all? Keeps "not recognized" noise off the screen.
where %1 >nul 2>nul || exit /b
REM Does it actually report a version? The Store stub says "Python was not
REM found", which deliberately does not match "Python 3".
%1 -V 2>&1 | findstr /b /c:"Python 3" >nul && set "PY=%1"
exit /b

:end
pause
