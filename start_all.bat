@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo  YouTube Script Generator - zero-install local mode
echo ============================================================

if not exist ".venv\Scripts\python.exe" (
  echo [1/5] Creating Python virtual environment ...
  where py >nul 2>nul
  if %errorlevel%==0 (
    py -3 -m venv .venv
  ) else (
    python -m venv .venv
  )
  if errorlevel 1 goto :fail
) else (
  echo [1/5] Virtual environment found
)

echo [2/5] Installing backend dependencies ...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :fail

echo [3/5] Preparing environment and database ...
".venv\Scripts\python.exe" scripts\bootstrap.py
if errorlevel 1 goto :fail

echo [4/5] Starting backend on http://127.0.0.1:8000 ...
start "YSG API" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

echo [5/5] Starting frontend on http://localhost:3000 ...
cd frontend
if not exist "node_modules" (
  echo Installing frontend dependencies ...
  call npm install
  if errorlevel 1 goto :fail
)
start "YSG Web" cmd /k "npm run dev"
cd ..

echo.
echo Waiting for the servers to boot ...
timeout /t 12 /nobreak >nul
start "" http://localhost:3000

echo.
echo Done. Two windows were opened (API + Web).
echo If the browser asks for an API key, copy it from the bootstrap output above.
echo Stop the servers by closing both windows.
exit /b 0

:fail
echo.
echo Startup failed. Fix the error above and run start_all.bat again.
pause
exit /b 1
