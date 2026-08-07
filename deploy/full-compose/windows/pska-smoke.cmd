@echo off
call "%~dp0_pska-wsl-run.cmd" "./bootstrap.sh smoke"
exit /b %ERRORLEVEL%
