$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

function Invoke-DockerChecked([string[]]$DockerArguments) {
    & docker @DockerArguments
    if ($LASTEXITCODE -ne 0) { throw "Docker command failed: $($DockerArguments[0])" }
}

function Get-OwnedListener([int]$Port, [string]$ScriptName, [bool]$Required) {
    $listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    if (-not $listeners.Count) {
        if ($Required) { throw "Expected original Windows service on $Port was not found." }
        return $null
    }
    $ownerIds = @($listeners.OwningProcess | Select-Object -Unique)
    if ($ownerIds.Count -ne 1) { throw "Unexpected listeners on $Port." }
    $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($ownerIds[0])"
    if (-not $owner.CommandLine.Contains($projectRoot) -or -not $owner.CommandLine.Contains($ScriptName)) {
        throw "Port $Port does not belong to the expected project service."
    }
    return $owner
}

function Stop-OwnedProcess($Process, [string]$ExpectedScript) {
    if (-not $Process) { return }
    $current = Get-CimInstance Win32_Process -Filter "ProcessId=$($Process.ProcessId)"
    if (-not $current) { return }
    if (-not $current.CommandLine.Contains($projectRoot) -or -not $current.CommandLine.Contains($ExpectedScript)) {
        throw 'Process identity changed; refusing to terminate it.'
    }
    & taskkill /PID $current.ProcessId /T /F | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Could not stop verified process $($current.ProcessId)." }
}

$previewHealth = & docker inspect --format '{{.State.Health.Status}}' toochuangai-single-app-1
if ($LASTEXITCODE -ne 0 -or $previewHealth -ne 'healthy') { throw 'Single-container preview is not healthy.' }
Invoke-DockerChecked @('compose','-f','compose.single.yaml','--env-file','.env','config','--quiet')
$mainProcess = Get-OwnedListener 8000 'app.py' $true
$xiaohaProcess = Get-OwnedListener 8501 'openrouter_image_site.py' $false
$xiaohaWatchdogs = @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe' OR Name='pwsh.exe'" | Where-Object {
    $_.CommandLine -and $_.CommandLine.Contains($projectRoot) -and $_.CommandLine.Contains('xiaoha_watchdog.ps1')
})
$tasks = @('TuChuangAI-Main','SellfoxAdDiagnosticSnapshotHourly','SellfoxAdsMonitorDaily') | ForEach-Object {
    $task = Get-ScheduledTask -TaskName $_
    $arguments = ($task.Actions | ForEach-Object { $_.Arguments }) -join ' '
    if (-not $arguments.Contains($projectRoot)) { throw "Task $_ does not belong to this project." }
    [pscustomobject]@{ Name=$task.TaskName; Enabled=[bool]$task.Settings.Enabled; Running=([int]$task.State -eq 4) }
}
$tasks | ConvertTo-Json | Set-Content -LiteralPath 'docker-data/cutover-task-state.json' -Encoding UTF8
$oldStopped = $false
try {
    Invoke-DockerChecked @('compose','-f','compose.single.yaml','--env-file','.env','stop','app')
    Invoke-DockerChecked @('compose','-f','compose.multi.yaml','--env-file','.env','down')
    $oldStopped = $true
    foreach ($task in $tasks) {
        Disable-ScheduledTask -TaskName $task.Name | Out-Null
        if ($task.Running) { Stop-ScheduledTask -TaskName $task.Name }
    }
    $adsRoot = Join-Path $projectRoot 'ads_monitor_web\ads-monitor-web-full-source'
    $oldCollectors = @(Get-CimInstance Win32_Process | Where-Object {
        $_.Name -match '^python(w)?\.exe$' -and $_.CommandLine -and $_.CommandLine.Contains($adsRoot) -and $_.CommandLine -match 'sellfox_ad_diagnostic_refresh\.py|sellfox_ads_monitor\.py'
    })
    foreach ($collector in $oldCollectors) {
        $scriptName = if ($collector.CommandLine.Contains('sellfox_ad_diagnostic_refresh.py')) { 'sellfox_ad_diagnostic_refresh.py' } else { 'sellfox_ads_monitor.py' }
        Stop-OwnedProcess $collector $scriptName
    }
    foreach ($watchdog in $xiaohaWatchdogs) { Stop-OwnedProcess $watchdog 'xiaoha_watchdog.ps1' }
    Stop-OwnedProcess $xiaohaProcess 'openrouter_image_site.py'
    Stop-OwnedProcess $mainProcess 'app.py'
    if (@(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue).Count) { throw 'Port 8000 is still occupied.' }
    $storageLine = Get-Content -LiteralPath '.env' -Encoding UTF8 | Where-Object { $_.StartsWith('DOCKER_STORAGE_PATH=') } | Select-Object -Last 1
    $storageRoot = $storageLine.Substring('DOCKER_STORAGE_PATH='.Length)
    foreach ($stateName in @('xiaotu_report_card_messages.json','ai_runtime_config.json')) {
        $sourceState = Join-Path $projectRoot $stateName
        $targetState = Join-Path $storageRoot $stateName
        if ((Test-Path -LiteralPath $sourceState) -and -not (Test-Path -LiteralPath $targetState)) {
            Copy-Item -LiteralPath $sourceState -Destination $targetState
        }
    }
    Invoke-DockerChecked @('compose','-f','compose.single.yaml','--env-file','.env','up','-d','--no-build','--force-recreate','--wait','--wait-timeout','240')
    Invoke-DockerChecked @('compose','-f','compose.single.yaml','--env-file','.env','exec','-T','app','python','/app/docker/healthcheck.py')
    Write-Output 'CUTOVER_SUCCEEDED'
} catch {
    Write-Warning 'Cutover failed; stopping the new container before restoring Windows services.'
    & docker compose -f compose.single.yaml --env-file .env stop app
    if ($LASTEXITCODE -ne 0) { throw 'New container could not be stopped; automatic Windows restore is withheld to prevent concurrent writes.' }
    if ($oldStopped) {
        foreach ($task in $tasks) {
            if ($task.Enabled) { Enable-ScheduledTask -TaskName $task.Name | Out-Null }
        }
        if (-not @(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue).Count) {
            Start-Process powershell.exe -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $projectRoot 'start_tuchuangai.ps1')) -WorkingDirectory $projectRoot -WindowStyle Hidden
        }
        if ($xiaohaProcess -and -not @(Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue).Count) {
            $pictureRoot = Get-ChildItem -LiteralPath $projectRoot -Directory | Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'xiaoha_watchdog.ps1') } | Select-Object -First 1
            Start-Process powershell.exe -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $pictureRoot.FullName 'xiaoha_watchdog.ps1')) -WorkingDirectory $projectRoot -WindowStyle Hidden
        }
        foreach ($task in $tasks) { if ($task.Enabled -and $task.Running) { Start-ScheduledTask -TaskName $task.Name } }
    }
    throw
}
