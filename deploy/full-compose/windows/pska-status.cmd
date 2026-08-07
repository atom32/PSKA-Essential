@echo off
call "%~dp0_pska-wsl-run.cmd" "./bootstrap.sh status"
exit /b %ERRORLEVEL%
