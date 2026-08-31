param(
    [ValidateRange(1, 25)]
    [int]$BatchSize = 1,
    [ValidateRange(1, 25)]
    [int]$DeepShopBatchSize = 8,
    [ValidateRange(1, 16)]
    [int]$CatalogWorkers = 3,
    [ValidateRange(1, 16)]
    [int]$OverviewWorkers = 4,
    [string]$SnapshotDir = "data\ad_diagnostic_snapshots",
    [ValidatePattern('^[0-9]{1,32}$')]
    [string]$PriorityShopId = "475394",
    [ValidatePattern('^[0-9]{1,32}$')]
    [string]$PriorityCampaignId = "70540977760495",
    [switch]$CheckConfig
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$pythonPath = if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
    $venvPython
} else {
    (Get-Command python.exe -ErrorAction Stop).Source
}
$scriptPath = Join-Path $projectRoot "sellfox_ad_diagnostic_refresh.py"
$dependencyPath = Join-Path $projectRoot ".python_deps"
$priorityStatusFile = Join-Path $projectRoot "data\ad_diagnostic_priority_refresh_status.json"
$resolvedSnapshotDir = if ([IO.Path]::IsPathRooted($SnapshotDir)) {
    [IO.Path]::GetFullPath($SnapshotDir)
} else {
    [IO.Path]::GetFullPath((Join-Path $projectRoot $SnapshotDir))
}

if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
    throw "Required file not found: $scriptPath"
}
if (Test-Path -LiteralPath $dependencyPath -PathType Container) {
    $separator = [IO.Path]::PathSeparator
    $env:PYTHONPATH = if ($env:PYTHONPATH) {
        "$dependencyPath$separator$env:PYTHONPATH"
    } else {
        $dependencyPath
    }
}

$refreshArgs = @(
    $scriptPath,
    "--snapshot-dir", $resolvedSnapshotDir,
    "--batch-size", $BatchSize,
    "--deep-shop-batch-size", $DeepShopBatchSize,
    "--catalog-workers", $CatalogWorkers,
    "--overview-workers", $OverviewWorkers
)
if ($CheckConfig) {
    $refreshArgs += "--check-config"
}

Push-Location $projectRoot
try {
    & $pythonPath @refreshArgs
    $catalogExitCode = $LASTEXITCODE
    if ($CheckConfig) {
        exit $catalogExitCode
    }

    $priorityArgs = @(
        $scriptPath,
        "--snapshot-dir", $resolvedSnapshotDir,
        "--status-file", $priorityStatusFile,
        "--shop-id", $PriorityShopId,
        "--campaign-id", $PriorityCampaignId,
        "--batch-size", 1,
        "--deep-shop-batch-size", 1,
        "--catalog-workers", 1,
        "--overview-workers", 1
    )
    & $pythonPath @priorityArgs
    $priorityExitCode = $LASTEXITCODE

    if ($catalogExitCode -ne 0) {
        exit $catalogExitCode
    }
    exit $priorityExitCode
} finally {
    Pop-Location
}
