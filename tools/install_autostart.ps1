# Регистрира refresh loop-а като Scheduled Task (стартира на logon, elevated).
# Пусни ВЕДНЪЖ от elevated PowerShell:  powershell -ExecutionPolicy Bypass -File tools\install_autostart.ps1
# Highest privileges -> loop-ът може да убива protected TURMO.exe и да хваща COM5.
$ErrorActionPreference = 'Stop'

$cmd = Join-Path $PSScriptRoot 'start.cmd'
if (-not (Test-Path $cmd)) { throw "Липсва $cmd" }

$action    = New-ScheduledTaskAction -Execute $cmd
$trigger   = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -RunLevel Highest -LogonType Interactive
$settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName 'ClaudeUsageDisplay' -Force `
    -Action $action -Trigger $trigger -Principal $principal -Settings $settings

Write-Host "Регистрирано: task 'ClaudeUsageDisplay' (стартира на logon, elevated)."
Write-Host "Пусни сега ръчно: Start-ScheduledTask -TaskName ClaudeUsageDisplay"
Write-Host "Махни:           Unregister-ScheduledTask -TaskName ClaudeUsageDisplay -Confirm:`$false"
