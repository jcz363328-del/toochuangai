param(
    [string]$TaskName = "SellfoxAdDiagnosticSnapshotHourly",
    [ValidateRange(30, 240)]
    [int]$IntervalMinutes = 60,
    [ValidateRange(1, 25)]
    [int]$BatchSize = 1,
    [ValidateRange(1, 25)]
    [int]$DeepShopBatchSize = 8,
    [ValidateRange(1, 16)]
    [int]$CatalogWorkers = 3,
    [ValidateRange(1, 1440)]
    [int]$CatalogTtlMinutes = 45,
    [ValidateRange(1, 16)]
    [int]$OverviewWorkers = 2,
    [string]$SnapshotDir = "data\ad_diagnostic_snapshots"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$runnerPath = Join-Path $projectRoot "运行广告诊断每小时刷新.ps1"
$resolvedSnapshotDir = if ([IO.Path]::IsPathRooted($SnapshotDir)) {
    [IO.Path]::GetFullPath($SnapshotDir)
} else {
    [IO.Path]::GetFullPath((Join-Path $projectRoot $SnapshotDir))
}

foreach ($path in @($runnerPath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required file not found: $path"
    }
}

$dpapiPath = Join-Path $env:LOCALAPPDATA "SellfoxTK\config.dpapi"
if (-not (Test-Path -LiteralPath $dpapiPath -PathType Leaf)) {
    throw "Stored DPAPI credentials not found. Run sellfox_import.py --configure first."
}

& $runnerPath -SnapshotDir $resolvedSnapshotDir -BatchSize $BatchSize -DeepShopBatchSize $DeepShopBatchSize -CatalogWorkers $CatalogWorkers -CatalogTtlMinutes $CatalogTtlMinutes -OverviewWorkers $OverviewWorkers -CheckConfig
if ($LASTEXITCODE -ne 0) {
    throw "Snapshot credential preflight failed; the task was not created."
}

$arguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" -SnapshotDir "{1}" -BatchSize {2} -DeepShopBatchSize {3} -CatalogWorkers {4} -CatalogTtlMinutes {5} -OverviewWorkers {6}' -f $runnerPath, $resolvedSnapshotDir, $BatchSize, $DeepShopBatchSize, $CatalogWorkers, $CatalogTtlMinutes, $OverviewWorkers
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument $arguments `
    -WorkingDirectory $projectRoot
$startAt = (Get-Date).AddMinutes(1)
while (($startAt.Minute % 15) -ne 10) {
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
    -ExecutionTimeLimit (New-TimeSpan -Minutes 59) `
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
    -Description "Sellfox all authorized shops hourly reports and validated snapshot refresh"
Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null

Write-Host "Created all-shop hourly reports and validated snapshot task: $TaskName"
Write-Host "Interval: every $IntervalMinutes minutes"
Write-Host "Campaigns per run: $BatchSize"
Write-Host "Deep-detail shops per run: $DeepShopBatchSize"
Write-Host "Catalog workers: $CatalogWorkers"
Write-Host "Overview workers: $OverviewWorkers"
Write-Host "First run: $startAt"
Write-Host "Snapshot directory: $resolvedSnapshotDir"
Write-Host "Run it now with: schtasks.exe /Run /TN `"$TaskName`""
