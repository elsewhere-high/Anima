param([ValidateSet('auto','cuda','cpu')][string]$Device='auto',[int]$Port=8768,[string]$ListenAddress='127.0.0.1',[ValidateSet('auto','ultra_light','balanced','best_edge')][string]$Profile='auto',[ValidateSet('auto','zh','yue')][string]$SpeechLanguage='auto')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Set-Location -LiteralPath $projectRoot
if ($ListenAddress -notin @('127.0.0.1','localhost','::1') -and -not $env:SOCIAL_API_TOKEN) { throw 'Set SOCIAL_API_TOKEN before exposing the server.' }
$env:PYTHONUTF8='1'
$env:PYTHONPATH=Join-Path $projectRoot 'v5'
$env:SOCIAL_DEVICE=$Device
$env:SOCIAL_PROFILE=$Profile
$env:SOCIAL_ASR_LANGUAGE=$SpeechLanguage
& (Join-Path $projectRoot '.venv_zh/Scripts/python.exe') -m uvicorn social_v5.server:app --host $ListenAddress --port $Port
exit $LASTEXITCODE
