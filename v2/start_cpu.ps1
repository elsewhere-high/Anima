$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:SOCIAL_DEVICE = 'cpu'
$env:HF_HUB_OFFLINE = '1'
& (Join-Path $PSScriptRoot '..\.venv_zh\Scripts\python.exe') -m uvicorn social_world_zh.server:app --host 127.0.0.1 --port 8766 --workers 1
