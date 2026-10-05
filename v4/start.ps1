param(
    [ValidateSet('cuda','cpu')][string]$Device='cuda',
    [int]$Port=8767,
    [string]$ListenAddress='127.0.0.1'
)
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path -LiteralPath 'v4/models/release.json')) { throw 'V4 release is not ready; inspect v4/reports and training logs.' }
if ($ListenAddress -notin @('127.0.0.1','localhost','::1') -and -not $env:SOCIAL_API_TOKEN) { throw 'Set SOCIAL_API_TOKEN before exposing the server on a network interface.' }
$env:PYTHONUTF8='1'
$env:PYTHONPATH=Join-Path $projectRoot 'v4'
$env:SOCIAL_DEVICE=$Device
& (Join-Path $projectRoot '.venv_zh/Scripts/python.exe') -m uvicorn social_v4.server:app --host $ListenAddress --port $Port
exit $LASTEXITCODE
