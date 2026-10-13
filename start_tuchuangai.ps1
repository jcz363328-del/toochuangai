$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonExe = 'C:\Python314\python.exe'
$appScript = Join-Path $projectRoot 'app.py'
$stdoutLog = Join-Path $projectRoot 'app_service_stdout.log'
$stderrLog = Join-Path $projectRoot 'app_service_stderr.log'
$launcherLog = Join-Path $projectRoot 'app_service_launcher.log'
$pidFile = Join-Path $projectRoot 'app_runtime.pid'

function Write-LauncherLog([string]$message) {
    $line = "$(Get-Date -Format o) $message`r`n"
    [System.IO.File]::AppendAllText(
        $launcherLog,
        $line,
        [System.Text.UTF8Encoding]::new($false)
    )
}

$env:PYTHONUNBUFFERED = '1'
Set-Location -LiteralPath $projectRoot

try {
    # Avoid duplicate case variants inherited from some shells, which can make
    # Start-Process reject the environment block on Windows.
    $pathValue = [Environment]::GetEnvironmentVariable(
        'Path',
        [EnvironmentVariableTarget]::Process
    )
    [Environment]::SetEnvironmentVariable(
        'PATH',
        $null,
        [EnvironmentVariableTarget]::Process
    )
    [Environment]::SetEnvironmentVariable(
        'Path',
        $pathValue,
        [EnvironmentVariableTarget]::Process
    )

    Write-LauncherLog 'starting app.py'
    $process = Start-Process `
        -FilePath $pythonExe `
        -ArgumentList @($appScript) `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutLog `
        -RedirectStandardError $stderrLog `
        -PassThru
    Set-Content -LiteralPath $pidFile -Value $process.Id -Encoding ASCII
    Write-LauncherLog "started pid=$($process.Id)"
    $process.WaitForExit()
    Write-LauncherLog "exited pid=$($process.Id) code=$($process.ExitCode)"
    exit $process.ExitCode
}
catch {
    Write-LauncherLog "launcher failed: $($_.Exception.Message)"
    exit 1
}
