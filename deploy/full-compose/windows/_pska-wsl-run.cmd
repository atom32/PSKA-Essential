@echo off
setlocal

set "PSKA_WSL_COMMAND=%~1"
if "%PSKA_WSL_COMMAND%"=="" (
  echo Missing WSL command.
  exit /b 2
)

if exist "%~dp0pska-demo-env.cmd" call "%~dp0pska-demo-env.cmd"

if "%PSKA_WSL_DISTRO%"=="" set "PSKA_WSL_DISTRO=Ubuntu-24.04"
if "%PSKA_WSL_COMPOSE_DIR%"=="" set "PSKA_WSL_COMPOSE_DIR=~/pska-demo/PSKA-Essential/deploy/full-compose"
if "%PSKA_FORCE_NO_PAUSE%"=="1" set "PSKA_NO_PAUSE=1"

echo.
echo PSKA WSL distro: %PSKA_WSL_DISTRO%
echo PSKA compose dir: %PSKA_WSL_COMPOSE_DIR%
echo Command: %PSKA_WSL_COMMAND%
echo.

wsl.exe -d "%PSKA_WSL_DISTRO%" -- bash -lc "set -e; cd %PSKA_WSL_COMPOSE_DIR%; %PSKA_WSL_COMMAND%"
set "PSKA_RC=%ERRORLEVEL%"

echo.
if "%PSKA_RC%"=="0" (
  echo Done.
) else (
  echo Failed with exit code %PSKA_RC%.
)

if not "%PSKA_NO_PAUSE%"=="1" pause
exit /b %PSKA_RC%
