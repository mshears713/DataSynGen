# Start uvicorn with port/host from backend/.env (API_PORT / API_HOST).
# Uvicorn's CLI ignores pydantic Settings; it reads UVICORN_PORT / UVICORN_HOST via Click.
# Usage (from backend): .\dev.ps1
# Extra args: .\dev.ps1 -- --log-level debug

param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemainingArguments
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Read-DotEnvKey {
    param(
        [string]$Path,
        [string]$Key
    )
    if (-not (Test-Path $Path)) { return $null }
    $keyUpper = $Key.ToUpperInvariant()
    foreach ($line in Get-Content -Path $Path -Encoding utf8) {
        $trimmed = ($line -split "#", 2)[0].Trim()
        if (-not $trimmed -or $trimmed -notmatch "=") { continue }
        $k, $v = $trimmed -split "=", 2
        $k = $k.Trim()
        if ($k.ToUpperInvariant() -ne $keyUpper) { continue }
        return $v.Trim().Trim('"').Trim("'")
    }
    return $null
}

$apiPort = Read-DotEnvKey ".env" "API_PORT"
$apiHost = Read-DotEnvKey ".env" "API_HOST"

if ($apiPort) {
    $env:UVICORN_PORT = $apiPort
    Write-Host "[dev.ps1] Set UVICORN_PORT=$apiPort (from API_PORT in .env)" -ForegroundColor Cyan
}
else {
    Write-Host "[dev.ps1] API_PORT not in .env; uvicorn default port 8000 applies unless you set UVICORN_PORT" -ForegroundColor Yellow
}

if ($apiHost) {
    $env:UVICORN_HOST = $apiHost
    Write-Host "[dev.ps1] Set UVICORN_HOST=$apiHost (from API_HOST in .env)" -ForegroundColor Cyan
}

$extra = [string[]]@()
if ($RemainingArguments) {
    $i = 0
    while ($i -lt $RemainingArguments.Count -and $RemainingArguments[$i] -eq "--") { $i++ }
    if ($i -lt $RemainingArguments.Count) {
        $extra = $RemainingArguments[$i..($RemainingArguments.Count - 1)]
    }
}
$allArgs = @("main:app", "--reload") + $extra
Write-Host "[dev.ps1] Running: uvicorn $($allArgs -join ' ')" -ForegroundColor DarkGray
& uvicorn @allArgs
