# Регистрира refresh loop-а като Scheduled Task (стартира на logon, elevated).
# Пусни ВЕДНЪЖ от elevated PowerShell:  powershell -ExecutionPolicy Bypass -File tools\install_autostart.ps1
# Highest privileges -> loop-ът може да убива protected TURMO.exe и да хваща COM5.
$ErrorActionPreference = 'Stop'

$cmd = Join-Path $PSScriptRoot 'start.cmd'
if (-not (Test-Path $cmd)) { throw "Липсва $cmd" }

$action    = New-ScheduledTaskAction -Execute $cmd

# Два trigger-а: старт при logon + watchdog на 10 мин. (MultipleInstances=IgnoreNew ->
# ако loop-ът върви, повторният старт се игнорира; ако е умрял, възкръсва до 10 мин.)
$logon    = New-ScheduledTaskTrigger -AtLogOn
$watchdog = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes 10) -RepetitionDuration (New-TimeSpan -Days 3650)

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -RunLevel Highest -LogonType Interactive
# ExecutionTimeLimit 0 = без лимит — иначе Windows тихо убива task-а след 72h (default)
# и RestartCount не помага, защото stop-ът не се брои за failure.
$settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName 'ClaudeUsageDisplay' -Force `
    -Action $action -Trigger @($logon, $watchdog) -Principal $principal -Settings $settings

Write-Host "Регистрирано: task 'ClaudeUsageDisplay' (стартира на logon, elevated)."
Write-Host "Пусни сега ръчно: Start-ScheduledTask -TaskName ClaudeUsageDisplay"
Write-Host "Махни:           Unregister-ScheduledTask -TaskName ClaudeUsageDisplay -Confirm:`$false"
