# Регистрира refresh loop-а като Scheduled Task (стартира на logon).
# Пусни ВЕДНЪЖ:  powershell -ExecutionPolicy Bypass -File tools\install_autostart.ps1
#
# -Target smalltv (default) -> LogonType Interactive, БЕЗ elevation (SmallTV е само HTTP).
# -Target turing|both       -> RunLevel Highest (нужен, за да убива protected TURMO.exe
#                              и да хваща COM5). Тогава пусни скрипта от ELEVATED PowerShell.
param([ValidateSet('smalltv','turing','both')][string]$Target = 'smalltv')
$ErrorActionPreference = 'Stop'

$cmd = Join-Path $PSScriptRoot 'start.cmd'
if (-not (Test-Path $cmd)) { throw "Липсва $cmd" }

$needsElevation = $Target -ne 'smalltv'

# Target-ът отива като аргумент към start.cmd (то го чете като %1 override).
$action    = New-ScheduledTaskAction -Execute $cmd -Argument $Target

# Два trigger-а: старт при logon + watchdog на 10 мин. (MultipleInstances=IgnoreNew ->
# ако loop-ът върви, повторният старт се игнорира; ако е умрял, възкръсва до 10 мин.)
$logon    = New-ScheduledTaskTrigger -AtLogOn
$watchdog = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes 10) -RepetitionDuration (New-TimeSpan -Days 3650)

$runLevel  = if ($needsElevation) { 'Highest' } else { 'Limited' }
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -RunLevel $runLevel -LogonType Interactive
# ExecutionTimeLimit 0 = без лимит — иначе Windows тихо убива task-а след 72h (default)
# и RestartCount не помага, защото stop-ът не се брои за failure.
$settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName 'ClaudeUsageDisplay' -Force `
    -Action $action -Trigger @($logon, $watchdog) -Principal $principal -Settings $settings

Write-Host "Регистрирано: task 'ClaudeUsageDisplay' (target=$Target, RunLevel=$runLevel, на logon)."
if ($needsElevation) {
    Write-Host "  ВНИМАНИЕ: target '$Target' иска elevation — ако не пусна скрипта от" -ForegroundColor Yellow
    Write-Host "  elevated PowerShell, task-ът няма да може да убива TURMO.exe." -ForegroundColor Yellow
}
Write-Host "Пусни сега ръчно: Start-ScheduledTask -TaskName ClaudeUsageDisplay"
Write-Host "Махни:           Unregister-ScheduledTask -TaskName ClaudeUsageDisplay -Confirm:`$false"
