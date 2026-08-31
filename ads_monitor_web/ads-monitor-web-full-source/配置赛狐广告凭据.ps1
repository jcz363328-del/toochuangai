param()

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Security
$appDir = Join-Path $env:LOCALAPPDATA "SellfoxTK"
$configPath = Join-Path $appDir "config.dpapi"
$stored = [ordered]@{}

if (Test-Path -LiteralPath $configPath -PathType Leaf) {
    $protected = [IO.File]::ReadAllBytes($configPath)
    $clear = [Security.Cryptography.ProtectedData]::Unprotect(
        $protected,
        $null,
        [Security.Cryptography.DataProtectionScope]::CurrentUser
    )
    $current = [Text.Encoding]::UTF8.GetString($clear) | ConvertFrom-Json
    foreach ($property in $current.PSObject.Properties) {
        $stored[$property.Name] = [string]$property.Value
    }
    [Array]::Clear($clear, 0, $clear.Length)
}

$clientId = (Read-Host "Sellfox client_id").Trim()
$secureSecret = Read-Host "Sellfox client_secret" -AsSecureString
$secretPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureSecret)
try {
    $clientSecret = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($secretPointer).Trim()
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($secretPointer)
}

if (-not $clientId -or -not $clientSecret) {
    throw "client_id and client_secret are required."
}

$stored["client_id"] = $clientId
$stored["client_secret"] = $clientSecret
$json = $stored | ConvertTo-Json -Compress
$clearBytes = [Text.Encoding]::UTF8.GetBytes($json)
try {
    $protectedBytes = [Security.Cryptography.ProtectedData]::Protect(
        $clearBytes,
        $null,
        [Security.Cryptography.DataProtectionScope]::CurrentUser
    )
    [IO.Directory]::CreateDirectory($appDir) | Out-Null
    $temporaryPath = Join-Path $appDir ("config.{0}.tmp" -f [Guid]::NewGuid().ToString("N"))
    try {
        [IO.File]::WriteAllBytes($temporaryPath, $protectedBytes)
        Move-Item -LiteralPath $temporaryPath -Destination $configPath -Force
    } finally {
        if (Test-Path -LiteralPath $temporaryPath) {
            Remove-Item -LiteralPath $temporaryPath -Force
        }
    }
} finally {
    [Array]::Clear($clearBytes, 0, $clearBytes.Length)
    $clientSecret = $null
}

Write-Host "Sellfox API credentials were encrypted with Windows DPAPI: $configPath"
