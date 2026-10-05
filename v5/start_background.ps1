$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$listener=Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue
if ($listener) { throw 'Port 8768 is already occupied; check /health before starting another service.' }
$env:PYTHONUTF8='1';$env:PYTHONPATH=Join-Path $projectRoot 'v5';$env:SOCIAL_DEVICE='cuda'
$serverProcess=Start-Process -FilePath (Join-Path $projectRoot '.venv_zh/Scripts/python.exe') -ArgumentList '-m','uvicorn','social_v5.server:app','--host','127.0.0.1','--port','8768' -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $PSScriptRoot 'reports/server_stdout.log') -RedirectStandardError (Join-Path $PSScriptRoot 'reports/server_stderr.log')
@{pid=$serverProcess.Id;port=8768;project=$projectRoot} | ConvertTo-Json | Set-Content (Join-Path $PSScriptRoot 'reports/server_process.json')
Write-Output "V5 starting on http://127.0.0.1:8768 (wrapper PID $($serverProcess.Id))"
