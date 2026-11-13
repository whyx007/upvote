# Local server launcher. First run generates a random secret key into .env (gitignored).
# Usage: pwsh -File scripts\serve.ps1 [-Port 8000]
param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$envFile = Join-Path $root '.env'

$key = $null
if (Test-Path $envFile) {
    $line = Get-Content $envFile | Where-Object { $_ -match '^UPVOTE_SECRET_KEY=(.+)$' } | Select-Object -First 1
    if ($line) { $key = $Matches[1] }
}
if (-not $key) {
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($bytes)
    $key = ([BitConverter]::ToString($bytes) -replace '-', '').ToLower()
    Add-Content -Path $envFile -Value "UPVOTE_SECRET_KEY=$key"
    Write-Host "Generated random secret key -> .env"
}

$env:UPVOTE_SECRET_KEY = $key
$dbPath = (Join-Path $root 'data\upvote.db') -replace '\\', '/'
$env:UPVOTE_DATABASE_URL = "sqlite:///$dbPath"
Set-Location (Join-Path $root 'backend')
Write-Host "Starting server on http://0.0.0.0:$Port (db: $dbPath)"
& (Join-Path $root '.venv\Scripts\python.exe') -m uvicorn app.main:create_app --factory --host 0.0.0.0 --port $Port