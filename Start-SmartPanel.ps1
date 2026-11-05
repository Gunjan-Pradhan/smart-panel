# ==============================================================================
# Smart Load Protection Panel — One-Command Startup Script
#
# Starts Docker containers (TimescaleDB, Mosquitto), runs migrations,
# starts the FastAPI backend, and launches the React dashboard.
# ==============================================================================

[CmdletBinding()]
param (
    [switch]$WithSimulator,
    [switch]$SkipDashboard
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "      SMART LOAD PROTECTION PANEL — FULL STACK INITIALIZATION         " -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan

# 1. Environment Verification
if (-not (Test-Path "$ProjectRoot\.env")) {
    if (Test-Path "$ProjectRoot\.env.example") {
        Write-Host "[!] .env not found. Creating from .env.example..." -ForegroundColor Yellow
        Copy-Item "$ProjectRoot\.env.example" "$ProjectRoot\.env"
    } else {
        Write-Error "No .env or .env.example file found!"
    }
}

# 2. Check & Start Docker Services
Write-Host "[1/5] Checking Docker Infrastructure (TimescaleDB + Mosquitto)..." -ForegroundColor Green
$dockerRunning = $false
try {
    $psOut = docker ps 2>&1
    if ($LASTEXITCODE -eq 0) { $dockerRunning = $true }
} catch {
    $dockerRunning = $false
}

if (-not $dockerRunning) {
    Write-Host "      Starting Docker Desktop engine..." -ForegroundColor Yellow
    $dockerDeskPath = "C:\Users\gunjan\AppData\Local\Programs\DockerDesktop\Docker Desktop.exe"
    if (Test-Path $dockerDeskPath) {
        Start-Process $dockerDeskPath
        Start-Sleep -Seconds 12
    }
}

# Start containers
Set-Location $ProjectRoot
docker compose up -d

# 3. Wait for PostgreSQL
Write-Host "[2/5] Waiting for TimescaleDB PostgreSQL to be ready on 127.0.0.1:5432..." -ForegroundColor Green
$retries = 30
while ($retries -gt 0) {
    $tcp = Test-NetConnection -ComputerName 127.0.0.1 -Port 5432 -WarningAction SilentlyContinue
    if ($tcp.TcpTestSucceeded) {
        Write-Host "      TimescaleDB is accepting connections!" -ForegroundColor Green
        break
    }
    Start-Sleep -Seconds 1
    $retries--
}

# 4. Run Alembic Database Migrations
Write-Host "[3/5] Applying Database Migrations (alembic upgrade head)..." -ForegroundColor Green
& "$ProjectRoot\.venv\Scripts\alembic.exe" upgrade head

# 5. Seed Admin User
Write-Host "[4/5] Verifying Admin Account..." -ForegroundColor Green
if (Test-Path "$ProjectRoot\scripts\create_admin.py") {
    & "$ProjectRoot\.venv\Scripts\python.exe" "$ProjectRoot\scripts\create_admin.py" 2>$null
}

# 6. Launch Services
Write-Host "[5/5] Launching FastAPI Backend & Dashboard..." -ForegroundColor Green

# Start Backend in new process
$backendJob = Start-Process -FilePath "$ProjectRoot\.venv\Scripts\uvicorn.exe" `
    -ArgumentList "app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload" `
    -WorkingDirectory $ProjectRoot `
    -PassThru

Write-Host "      Backend running at: http://127.0.0.1:8000 (API Docs: http://127.0.0.1:8000/docs)" -ForegroundColor Cyan

# Start Dashboard unless skipped
if (-not $SkipDashboard) {
    $dashJob = Start-Process -FilePath "cmd.exe" `
        -ArgumentList "/c npm run dev" `
        -WorkingDirectory "$ProjectRoot\dashboard" `
        -PassThru
    Write-Host "      Dashboard running at: http://localhost:5173" -ForegroundColor Cyan
}

# Optionally launch simulator
if ($WithSimulator) {
    Write-Host "      Starting Hardware Simulator (PANEL-0001)..." -ForegroundColor Yellow
    $simJob = Start-Process -FilePath "$ProjectRoot\.venv\Scripts\python.exe" `
        -ArgumentList "simulator/telemetry_simulator.py --device-id PANEL-0001" `
        -WorkingDirectory $ProjectRoot `
        -PassThru
}

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Green
Write-Host "  ALL SYSTEMS ONLINE — SMART LOAD PROTECTION PANEL READY!              " -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Green
Write-Host "  - Web Dashboard:     http://localhost:5173" -ForegroundColor White
Write-Host "  - Swagger API Docs:  http://127.0.0.1:8000/docs" -ForegroundColor White
Write-Host "  - Health Check:      http://127.0.0.1:8000/health" -ForegroundColor White
Write-Host "  - Mosquitto MQTT:    127.0.0.1:1883" -ForegroundColor White
Write-Host "  - TimescaleDB:       127.0.0.1:5432 (smart_panel)" -ForegroundColor White
Write-Host "======================================================================" -ForegroundColor Green

