param(
    [int]$ApiPort = 4311
)

$ErrorActionPreference = "Stop"
$projectDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$healthUrl = "http://127.0.0.1:$ApiPort/api/health"
$runtimeRoot = if ($env:TUCHUANGAI_STORAGE_ROOT) {
    Join-Path $env:TUCHUANGAI_STORAGE_ROOT "business-analysis"
} else {
    Join-Path ([System.IO.Path]::GetTempPath()) "toochuangai-business-analysis"
}
$logDir = Join-Path $runtimeRoot "logs"
$stdoutLog = Join-Path $logDir "api.out.log"
$stderrLog = Join-Path $logDir "api.err.log"
$mutexName = "Global\ToochuangBusinessAnalysisApi$ApiPort"

New-Item -ItemType Directory -Path $logDir -Force | Out-Null

function Test-ApiHealth {
    try {
        $response = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 3
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 400
    } catch {
        return $false
    }
}

$mutex = New-Object System.Threading.Mutex($false, $mutexName)
$lockTaken = $false

try {
    try {
        $lockTaken = $mutex.WaitOne(0, $false)
    } catch [System.Threading.AbandonedMutexException] {
        $lockTaken = $true
    }
    if (-not $lockTaken -or (Test-ApiHealth)) { exit 0 }

    # Some Windows hosts expose both `Path` and `PATH`. Start-Process builds a
    # case-insensitive environment dictionary and otherwise fails before the
    # API child process is created.
    $processPath = $env:Path
    Remove-Item Env:PATH -ErrorAction SilentlyContinue
    $env:Path = $processPath

    $node = (Get-Command "node.exe" -ErrorAction Stop).Source
    $mssqlPackage = Join-Path $projectDir "node_modules\mssql\package.json"
    if (-not (Test-Path -LiteralPath $mssqlPackage)) {
        $npm = (Get-Command "npm.cmd" -ErrorAction Stop).Source
        & $npm ci --omit=dev --no-audit --no-fund --prefix $projectDir
        if ($LASTEXITCODE -ne 0) { throw "npm ci failed with exit code $LASTEXITCODE" }
    }

    $process = Start-Process `
        -FilePath $node `
        -ArgumentList @("server/index.mjs") `
        -WorkingDirectory $projectDir `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutLog `
        -RedirectStandardError $stderrLog `
        -PassThru

    for ($attempt = 0; $attempt -lt 20; $attempt += 1) {
        Start-Sleep -Milliseconds 500
        if (Test-ApiHealth) { exit 0 }
        if ($process.HasExited) { throw "API process exited with code $($process.ExitCode)" }
    }
    throw "API did not become healthy within 10 seconds"
} finally {
    if ($lockTaken) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
