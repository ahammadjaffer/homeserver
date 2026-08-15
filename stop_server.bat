@echo off
echo Stopping NitroStream Stack...

REM Stop Nginx
cd /d C:\nginx
nginx -s stop

REM Terminate Python processes (Waitress and Huey)
taskkill /F /IM python.exe /T

echo All services stopped cleanly.
pause