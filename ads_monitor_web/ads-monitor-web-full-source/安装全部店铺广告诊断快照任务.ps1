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
    [ValidateRange(1, 16)]
    [int]$OverviewWorkers = 4,
    [string]$SnapshotDir = "data\ad_diagnostic_snapshots"
)

$ErrorActionPreference = "Stop"
$installerPath = Join-Path $PSScriptRoot "install_ads_diagnostic_hourly_task.ps1"
& $installerPath `
    -TaskName $TaskName `
    -IntervalMinutes $IntervalMinutes `
    -BatchSize $BatchSize `
    -DeepShopBatchSize $DeepShopBatchSize `
    -CatalogWorkers $CatalogWorkers `
    -OverviewWorkers $OverviewWorkers `
    -SnapshotDir $SnapshotDir
exit $LASTEXITCODE
