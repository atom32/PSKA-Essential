@echo off
setlocal

if exist "%~dp0pska-demo-env.cmd" call "%~dp0pska-demo-env.cmd"
if "%PSKA_WSL_DISTRO%"=="" set "PSKA_WSL_DISTRO=Ubuntu-24.04"

echo.
echo Refreshing Windows portproxy for WSL distro: %PSKA_WSL_DISTRO%
echo This command requires an Administrator terminal.
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0refresh-wsl-portproxy.ps1" -Distro "%PSKA_WSL_DISTRO%"
set "PSKA_RC=%ERRORLEVEL%"

echo.
if "%PSKA_RC%"=="0" (
  echo Done.
) else (
  echo Failed with exit code %PSKA_RC%.
)

if not "%PSKA_NO_PAUSE%"=="1" pause
exit /b %PSKA_RC%
