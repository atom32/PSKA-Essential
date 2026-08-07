@echo off
call "%~dp0_pska-wsl-run.cmd" "./bootstrap.sh sidecars && ./bootstrap.sh status"
exit /b %ERRORLEVEL%
