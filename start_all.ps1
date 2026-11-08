# YouTube Script Generator - zero-install local mode (PowerShell)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " YouTube Script Generator - local mode" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "[1/5] Creating Python virtual environment ..."
    if (Get-Command py -ErrorAction SilentlyContinue) {
        py -3 -m venv .venv
    } else {
        python -m venv .venv
    }
} else {
    Write-Host "[1/5] Virtual environment found"
}

Write-Host "[2/5] Installing backend dependencies ..."
& $venvPython -m pip install --upgrade pip | Out-Null
& $venvPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

Write-Host "[3/5] Preparing environment and database ..."
& $venvPython scripts\bootstrap.py
if ($LASTEXITCODE -ne 0) { throw "bootstrap failed" }

Write-Host "[4/5] Starting backend on http://127.0.0.1:8000 ..."
$apiCommand = "& '$venvPython' -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $apiCommand

Write-Host "[5/5] Starting frontend on http://localhost:3000 ..."
if (-not (Test-Path (Join-Path $PSScriptRoot "frontend\node_modules"))) {
    Push-Location frontend
    npm install
    Pop-Location
    if ($LASTEXITCODE -ne 0) { throw "npm install failed" }
}
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$PSScriptRoot\frontend'; npm run dev"

Write-Host "Waiting for the servers to boot ..."
Start-Sleep -Seconds 12
Start-Process "http://localhost:3000"

Write-Host ""
Write-Host "Done. Two windows were opened (API + Web)." -ForegroundColor Green
Write-Host "If the app asks for an API key, copy it from the bootstrap output above."
Write-Host "Stop the servers by closing both windows."
