@echo off
setlocal

set "PSKA_FORCE_NO_PAUSE=1"
call "%~dp0_pska-wsl-run.cmd" "./bootstrap.sh down"
set "PSKA_RC=%ERRORLEVEL%"
if not "%PSKA_RC%"=="0" (
  echo.
  echo PSKA stop failed with exit code %PSKA_RC%. WSL was not shut down.
  pause
  exit /b %PSKA_RC%
)

echo.
echo Shutting down all WSL distros and the WSL2 VM...
wsl.exe --shutdown
set "PSKA_RC=%ERRORLEVEL%"

echo.
if "%PSKA_RC%"=="0" (
  echo WSL shutdown requested.
) else (
  echo wsl --shutdown failed with exit code %PSKA_RC%.
)
pause
exit /b %PSKA_RC%
