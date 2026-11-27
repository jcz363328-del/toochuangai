param(
    [int]$CheckIntervalSeconds = 15,
    [int]$ConsecutiveFailureThreshold = 3,
    [switch]$OpenBrowser
)

$ErrorActionPreference = "Stop"

# Some launchers inject both `Path` and `PATH`. Start-Process treats them as
# duplicate keys on Windows, so normalize the process environment first.
$processPathValue = [Environment]::GetEnvironmentVariable("Path", [EnvironmentVariableTarget]::Process)
[Environment]::SetEnvironmentVariable("PATH", $null, [EnvironmentVariableTarget]::Process)
[Environment]::SetEnvironmentVariable("Path", $processPathValue, [EnvironmentVariableTarget]::Process)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$appScript = Join-Path $scriptDir "openrouter_image_site.py"
$healthUrl = "http://127.0.0.1:8501/lashforge/"
$publicUrl = "http://www.toochuangai.com:8501/lashforge/"
$dataRoot = if ($env:XIAOHA_DATA_ROOT) { $env:XIAOHA_DATA_ROOT } else { "D:\toochuangai\_non_code_files\xiaoha" }
$canvasBuildDir = if ($env:INFINITE_CANVAS_BUILD_DIR) { $env:INFINITE_CANVAS_BUILD_DIR } else { "D:\toochuangai\_non_code_files\infinite-canvas\build" }
$logDir = Join-Path $dataRoot "logs"
$logFile = Join-Path $logDir "xiaoha-watchdog.log"
$serviceOutLog = Join-Path $logDir "xiaoha.out.log"
$serviceErrLog = Join-Path $logDir "xiaoha.err.log"
$pidFile = Join-Path $dataRoot "xiaoha.pid"
$mutexName = "Global\XiaoHaWatchdog8501"

foreach ($directory in @($dataRoot, $logDir, $canvasBuildDir)) {
    if (-not (Test-Path -LiteralPath $directory)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }
}

function Write-Log {
    param([string]$Message)

    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[{0}] {1}" -f $timestamp, $Message
    Add-Content -Path $logFile -Value $line -Encoding UTF8
    Write-Host $line
}

function Test-XiaoHaHealth {
    try {
        $response = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 8
        return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400)
    } catch {
        return $false
    }
}

function Stop-XiaoHaProcess {
    if (-not (Test-Path -LiteralPath $pidFile)) {
        return
    }
    $managedPid = [int](Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($managedPid -gt 0) {
        try {
            Stop-Process -Id $managedPid -Force -ErrorAction Stop
            Write-Log ("Stopped stale XiaoHa process PID={0}" -f $managedPid)
        } catch {
            Write-Log ("Managed XiaoHa process PID={0} was already stopped" -f $managedPid)
        }
    }
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
}

function Start-XiaoHaProcess {
    if (-not (Test-Path -LiteralPath $appScript)) {
        throw "XiaoHa application was not found: $appScript"
    }
    if (-not (Get-Command "python" -ErrorAction SilentlyContinue)) {
        throw "Python is not available in PATH"
    }

    $env:INFINITE_CANVAS_BUILD_DIR = $canvasBuildDir
    $arguments = @(
        "-m",
        "streamlit",
        "run",
        $appScript,
        "--server.address",
        "0.0.0.0",
        "--server.port",
        "8501",
        "--server.baseUrlPath",
        "lashforge",
        "--server.headless",
        "true",
        "--server.websocketPingInterval",
        "20",
        "--server.disconnectedSessionTTL",
        "86400",
        "--server.fileWatcherType",
        "none"
    )

    $process = Start-Process `
        -FilePath "python" `
        -ArgumentList $arguments `
        -WorkingDirectory $scriptDir `
        -WindowStyle Hidden `
        -RedirectStandardOutput $serviceOutLog `
        -RedirectStandardError $serviceErrLog `
        -PassThru

    Set-Content -LiteralPath $pidFile -Value $process.Id -Encoding ASCII
    Write-Log ("Started XiaoHa process PID={0}" -f $process.Id)
}

$mutex = New-Object System.Threading.Mutex($false, $mutexName)
$lockTaken = $false

try {
    try {
        $lockTaken = $mutex.WaitOne(0, $false)
    } catch [System.Threading.AbandonedMutexException] {
        $lockTaken = $true
    }

    if (-not $lockTaken) {
        Write-Host "XiaoHa watchdog is already running."
        exit 0
    }

    Write-Log ("XiaoHa watchdog started; data root: {0}" -f $dataRoot)
    $browserOpened = $false
    $consecutiveFailures = 0
    $failureThreshold = [Math]::Max(1, $ConsecutiveFailureThreshold)

    while ($true) {
        if (-not (Test-XiaoHaHealth)) {
            $consecutiveFailures += 1
            Write-Log ("Health check failed ({0}/{1}); keeping the current process until the threshold is reached" -f $consecutiveFailures, $failureThreshold)
            if ($consecutiveFailures -ge $failureThreshold) {
                Write-Log "Health check failure threshold reached, restarting service"
                Stop-XiaoHaProcess
                Start-XiaoHaProcess
                Start-Sleep -Seconds 8
                if (Test-XiaoHaHealth) {
                    Write-Log "Service recovered successfully"
                    $consecutiveFailures = 0
                } else {
                    Write-Log "Service restart attempted but health check is still failing"
                }
            }
        } else {
            if ($consecutiveFailures -gt 0) {
                Write-Log "Health check recovered without restarting the service"
                $consecutiveFailures = 0
            }
            if (-not $browserOpened -and $OpenBrowser) {
                Start-Process $publicUrl
                $browserOpened = $true
                Write-Log "Opened XiaoHa URL in browser"
            }
        }

        Start-Sleep -Seconds $CheckIntervalSeconds
    }
} finally {
    if ($lockTaken -and $mutex) {
        $mutex.ReleaseMutex()
    }
    if ($mutex) {
        $mutex.Dispose()
    }
}
