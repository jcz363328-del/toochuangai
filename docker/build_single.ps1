$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path -LiteralPath '.env')) {
    throw 'Create .env from .env.example and fill in credentials first.'
}
python docker/prepare_runtime.py
if ($LASTEXITCODE -ne 0) { throw 'Runtime configuration preparation failed.' }
docker compose -f compose.multi.yaml --env-file .env build
if ($LASTEXITCODE -ne 0) { throw 'Component image build failed.' }
foreach ($volumeName in @('knowledge-base','listing-data','sales-data','exports','runtime-logs','xiaoha-history','xiaoha-outputs','video-data','video-results','video-temp','ads-data','ads-outputs')) {
    docker volume create "toochuangai-docker_$volumeName" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Volume preparation failed: $volumeName" }
}
docker compose -f compose.single.yaml --env-file .env build
if ($LASTEXITCODE -ne 0) { throw 'Single container image build failed.' }
