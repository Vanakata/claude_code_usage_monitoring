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

# --- 5. ccusage (for SESSION cost/tokens) - auto-install if Node is present ---
if (Get-Command ccusage -ErrorAction SilentlyContinue) {
    Write-Host "[setup] ccusage: found" -ForegroundColor Green
} elseif (Get-Command npm -ErrorAction SilentlyContinue) {
    Write-Host "[setup] ccusage missing - installing via npm..." -ForegroundColor Yellow
    try { npm install -g ccusage | Out-Null } catch {}
    if (Get-Command ccusage -ErrorAction SilentlyContinue) {
        Write-Host "[setup] ccusage: installed" -ForegroundColor Green
    } else {
        Write-Host "[setup] ccusage install failed - run manually: npm i -g ccusage" -ForegroundColor Yellow
    }
} else {
    Write-Host "[setup] ccusage missing and no Node.js found." -ForegroundColor Yellow
    Write-Host "        SESSION/CTX/BURN need it: install Node (nodejs.org) then npm i -g ccusage." -ForegroundColor Yellow
    Write-Host "        The 5h/WK gauges (and SmallTV) work without it." -ForegroundColor Yellow
}

# --- 6. Desktop shortcut (double-clickable start) ---
try {
    $startCmd = Join-Path $root "tools\start.cmd"
    $desktop  = [Environment]::GetFolderPath('Desktop')
    $lnk      = Join-Path $desktop "Claude Usage Display.lnk"
    $ws = New-Object -ComObject WScript.Shell
    $sc = $ws.CreateShortcut($lnk)
    $sc.TargetPath       = $startCmd
    $sc.WorkingDirectory = $root
    $sc.Description       = "Start Claude usage display loop"
    $sc.Save()
    Write-Host "[setup] Desktop shortcut created: 'Claude Usage Display'" -ForegroundColor Green
} catch {
    Write-Host "[setup] Could not create desktop shortcut (skipping): $_" -ForegroundColor Yellow
}

# --- 7. Preflight doctor ---
Write-Host ""
Write-Host "[setup] Running preflight check (doctor)..." -ForegroundColor Cyan
& $venvPy (Join-Path $root "doctor.py")

# --- Done ---
Write-Host ""
Write-Host "[setup] DONE. To start the display, either:" -ForegroundColor Cyan
Write-Host "  - double-click 'Claude Usage Display' on your Desktop, or"
Write-Host "  - run:  .\.venv\Scripts\python.exe run.py"
Write-Host ""
Write-Host "Autostart on logon (SmallTV needs no admin; Turing needs elevated for TURMO):" -ForegroundColor Cyan
Write-Host "  powershell -ExecutionPolicy Bypass -File tools\install_autostart.ps1"
Write-Host "  Start-ScheduledTask -TaskName ClaudeUsageDisplay"
