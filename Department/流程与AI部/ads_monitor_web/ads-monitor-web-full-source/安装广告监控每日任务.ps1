param(
    [string]$TaskName = "SellfoxAdsMonitorDaily",
    [ValidatePattern('^([01]\d|2[0-3]):[0-5]\d$')]
    [string]$At = "09:00",
    [string]$ConfigPath = "ads_monitor_config.json",
    [ValidateRange(0, 240)]
    [int]$LockWaitMinutes = 90
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$pythonPath = if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
    $venvPython
} else {
    (Get-Command python.exe -ErrorAction Stop).Source
}
$scriptPath = Join-Path $projectRoot "sellfox_ads_monitor.py"
$scheduledOutputPath = Join-Path $projectRoot "outputs\ads_monitor_scheduled"
$resolvedConfigPath = if ([IO.Path]::IsPathRooted($ConfigPath)) {
    [IO.Path]::GetFullPath($ConfigPath)
} else {
    [IO.Path]::GetFullPath((Join-Path $projectRoot $ConfigPath))
}

if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
    throw "Monitor script not found: $scriptPath"
}
if (-not (Test-Path -LiteralPath $resolvedConfigPath -PathType Leaf)) {
    throw "Monitor config not found: $resolvedConfigPath"
}

$dpapiPath = Join-Path $env:LOCALAPPDATA "SellfoxTK\config.dpapi"
if (-not (Test-Path -LiteralPath $dpapiPath -PathType Leaf)) {
    throw "Stored DPAPI credentials not found. Run sellfox_import.py --configure first."
}

$credentialVariables = @("SELLFOX_CLIENT_ID", "SELLFOX_CLIENT_SECRET")
$savedCredentials = @{}
foreach ($name in $credentialVariables) {
    $savedCredentials[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
    [Environment]::SetEnvironmentVariable($name, $null, "Process")
}
try {
    & $pythonPath $scriptPath --config $resolvedConfigPath --check-config --no-workbook
    if ($LASTEXITCODE -ne 0) {
        throw "Stored-credential preflight failed; the scheduled task was not created."
    }
} finally {
    foreach ($name in $credentialVariables) {
        [Environment]::SetEnvironmentVariable($name, $savedCredentials[$name], "Process")
    }
}

$currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$arguments = '"{0}" --config "{1}" --output-dir "{2}" --once --no-workbook --lock-wait-minutes {3}' -f $scriptPath, $resolvedConfigPath, $scheduledOutputPath, $LockWaitMinutes
$action = New-ScheduledTaskAction `
    -Execute $pythonPath `
    -Argument $arguments `
    -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -WakeToRun `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 15) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 6) `
    -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal `
    -UserId $currentUser `
    -LogonType Interactive `
    -RunLevel Limited
$task = New-ScheduledTask `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Sellfox all-shop live ads dashboard refresh (read-only, waits for hourly snapshot lock)"
Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null

Write-Host "Created daily live-dashboard task: $TaskName at $At"
Write-Host "User context: $currentUser (must be signed in)"
Write-Host "Config: $resolvedConfigPath"
Write-Host "Scheduled output: $scheduledOutputPath"
Write-Host "Lock wait: $LockWaitMinutes minutes"
Write-Host "Run it now with:"
Write-Host ('schtasks.exe /Run /TN "{0}"' -f $TaskName)
