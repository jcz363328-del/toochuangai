param(
    [string]$TaskName = "SellfoxAdsRealtime15Min",
    [ValidateRange(15, 60)]
    [int]$IntervalMinutes = 15,
    [string]$ConfigPath = "ads_monitor_config.json"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$scriptPath = Join-Path $projectRoot "sellfox_ads_realtime.py"
$resolvedConfigPath = if ([IO.Path]::IsPathRooted($ConfigPath)) {
    [IO.Path]::GetFullPath($ConfigPath)
} else {
    [IO.Path]::GetFullPath((Join-Path $projectRoot $ConfigPath))
}

foreach ($path in @($pythonPath, $scriptPath, $resolvedConfigPath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required file not found: $path"
    }
}

$dpapiPath = Join-Path $env:LOCALAPPDATA "SellfoxTK\config.dpapi"
if (-not (Test-Path -LiteralPath $dpapiPath -PathType Leaf)) {
    throw "Stored DPAPI credentials not found. Run sellfox_import.py --configure first."
}

& $pythonPath $scriptPath --config $resolvedConfigPath --plan-only
if ($LASTEXITCODE -ne 0) {
    throw "Realtime plan preflight failed; the scheduled task was not created."
}

$arguments = '"{0}" --config "{1}"' -f $scriptPath, $resolvedConfigPath
$action = New-ScheduledTaskAction `
    -Execute $pythonPath `
    -Argument $arguments `
    -WorkingDirectory $projectRoot
$startAt = (Get-Date).AddMinutes(1)
while (($startAt.Minute % 15) -ne 5) {
    $startAt = $startAt.AddMinutes(1)
}
$startAt = Get-Date -Year $startAt.Year -Month $startAt.Month -Day $startAt.Day `
    -Hour $startAt.Hour -Minute $startAt.Minute -Second 0
$trigger = New-ScheduledTaskTrigger `
    -Once `
    -At $startAt `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -WakeToRun `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 12) `
    -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries
$currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal `
    -UserId $currentUser `
    -LogonType Interactive `
    -RunLevel Limited
$task = New-ScheduledTask `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Sellfox SP provisional hourly monitor; read-only warning and blocking layer"
Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null

Write-Host "Created read-only realtime task: $TaskName"
Write-Host "Interval: every $IntervalMinutes minutes"
Write-Host "First run: $startAt (fixed away from the 09:00 mature-layer start)"
Write-Host "User context: $currentUser (must be signed in)"
Write-Host "Run it now with: schtasks.exe /Run /TN `"$TaskName`""
