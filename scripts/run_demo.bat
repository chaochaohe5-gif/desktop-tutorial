@echo off
setlocal
cd /d "%~dp0.."
set PYTHONUTF8=1
set "demo_output=output\demo-%RANDOM%-%RANDOM%"
where py >nul 2>&1
if errorlevel 1 (
  python -m manju build examples/episode.json --out "%demo_output%"
) else (
  py -3 -m manju build examples/episode.json --out "%demo_output%"
)
if errorlevel 1 (
  echo Failed. Install Python 3.11+ or check the error above.
  pause
  exit /b 2
)
explorer "%demo_output%"
pause
