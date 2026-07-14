param(
    [int]$CheckIntervalSeconds = 15,
    [switch]$OpenBrowser
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$appScript = Join-Path $scriptDir "openrouter_image_site.py"
$healthUrl = "http://127.0.0.1:8501/lashforge/"
$publicUrl = "http://www.toochuangai.com:8501/lashforge/"
$logDir = Join-Path $scriptDir ".watchdog"
$logFile = Join-Path $logDir "xiaoha-watchdog.log"
$mutexName = "Global\XiaoHaWatchdog8501"

if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
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

function Get-XiaoHaProcesses {
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.Name -match "^python(w)?(\.exe)?$" -and
            $_.CommandLine -and
            $_.CommandLine -match [regex]::Escape("openrouter_image_site.py")
        }
}

function Stop-XiaoHaProcesses {
    $processes = @(Get-XiaoHaProcesses)
    foreach ($process in $processes) {
        try {
            Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
            Write-Log ("Stopped stale process PID={0}" -f $process.ProcessId)
        } catch {
            Write-Log ("Failed to stop PID={0}: {1}" -f $process.ProcessId, $_.Exception.Message)
        }
    }
}

function Start-XiaoHaProcess {
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
        "true"
    )

    $process = Start-Process `
        -FilePath "python" `
        -ArgumentList $arguments `
        -WorkingDirectory $scriptDir `
        -WindowStyle Minimized `
        -PassThru

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

    Write-Log "XiaoHa watchdog started"

    $browserOpened = $false

    while ($true) {
        if (-not (Test-XiaoHaHealth)) {
            Write-Log "Health check failed, restarting service"
            Stop-XiaoHaProcesses
            Start-XiaoHaProcess
            Start-Sleep -Seconds 8
            if (Test-XiaoHaHealth) {
                Write-Log "Service recovered successfully"
            } else {
                Write-Log "Service restart attempted but health check is still failing"
            }
        } elseif (-not $browserOpened -and $OpenBrowser) {
            Start-Process $publicUrl
            $browserOpened = $true
            Write-Log "Opened XiaoHa URL in browser"
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
