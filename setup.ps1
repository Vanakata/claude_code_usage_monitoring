# setup.ps1 - one-shot setup for claude_code_usage_monitoring (Windows)
# Run from the project root:
#   powershell -ExecutionPolicy Bypass -File setup.ps1
#
# Does: clone the driver library + create .venv + install deps + checks.
# Idempotent - safe to re-run (skips what is already done).
# (ASCII-only on purpose: PowerShell 5.1 reads .ps1 as ANSI, so no Cyrillic here.)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
Set-Location $root
Write-Host "[setup] claude_code_usage_monitoring" -ForegroundColor Cyan

# --- 1. Find Python 3.x (<= 3.13; the library rejects 3.14+ on Windows) ---
$candidates = @(@('py', '-3.13'), @('py', '-3.12'), @('py', '-3.11'), @('python'))
$pyExe = $null; $pyArgs = @()
foreach ($c in $candidates) {
    $exe = $c[0]
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
    $rest = @(); if ($c.Count -gt 1) { $rest = $c[1..($c.Count - 1)] }
    try { $ver = (& $exe @rest --version) 2>&1 | Out-String } catch { continue }
    if ($ver -match 'Python 3\.(\d+)') {
        if ([int]$Matches[1] -le 13) { $pyExe = $exe; $pyArgs = $rest; break }
    }
}
if (-not $pyExe) { throw "No suitable Python (need 3.x <= 3.13). See python.org." }
Write-Host "[setup] Python: $pyExe $($pyArgs -join ' ')" -ForegroundColor Green

# --- 2. Clone the driver library (gitignored) ---
if (Test-Path "turing-smart-screen-python") {
    Write-Host "[setup] turing-smart-screen-python already present - skipping"
} else {
    Write-Host "[setup] cloning turing-smart-screen-python..."
    git clone https://github.com/mathoudebine/turing-smart-screen-python.git
    if ($LASTEXITCODE -ne 0) { throw "git clone failed" }
}

# --- 3. venv ---
if (-not (Test-Path ".venv")) {
    Write-Host "[setup] creating .venv..."
    & $pyExe @pyArgs -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "venv creation failed" }
}
$venvPy = Join-Path $root ".venv\Scripts\python.exe"

# --- 4. Dependencies ---
Write-Host "[setup] installing deps (pyserial, Pillow, numpy)..."
& $venvPy -m pip install --quiet --upgrade pip
& $venvPy -m pip install --quiet pyserial Pillow numpy
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

# --- 5. ccusage (optional - for SESSION cost/tokens) ---
if (Get-Command ccusage -ErrorAction SilentlyContinue) {
    Write-Host "[setup] ccusage: found" -ForegroundColor Green
} else {
    Write-Host "[setup] ccusage missing - for SESSION cost/tokens run: npm i -g ccusage" -ForegroundColor Yellow
    Write-Host "        (the 5h/WK gauges work without it)" -ForegroundColor Yellow
}

# --- Done ---
Write-Host ""
Write-Host "[setup] DONE. Plug in the monitor and run:" -ForegroundColor Cyan
Write-Host "  .\.venv\Scripts\python.exe run.py"
Write-Host ""
Write-Host "Autostart (elevated PowerShell):" -ForegroundColor Cyan
Write-Host "  powershell -ExecutionPolicy Bypass -File tools\install_autostart.ps1"
Write-Host "  Start-ScheduledTask -TaskName ClaudeUsageDisplay"
