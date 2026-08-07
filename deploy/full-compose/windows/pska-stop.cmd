@echo off
call "%~dp0_pska-wsl-run.cmd" "./bootstrap.sh down"
exit /b %ERRORLEVEL%
