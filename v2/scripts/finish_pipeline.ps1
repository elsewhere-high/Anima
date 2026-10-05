$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location -LiteralPath $projectRoot
$pythonExe = Join-Path $projectRoot '.venv_zh\Scripts\python.exe'
$pipelineStatus = Join-Path $projectRoot 'v2\reports\pipeline_status.txt'
'Waiting for training process to finish' | Set-Content -LiteralPath $pipelineStatus -Encoding utf8
while (Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object { $_.CommandLine -like '*v2/scripts/train.py*' }) { Start-Sleep -Seconds 10 }
$events = Get-Content -LiteralPath 'v2/reports/train_events.jsonl' -Tail 1 | ConvertFrom-Json
if ($events.type -ne 'complete') { throw 'Training did not record successful completion' }
$stages = @(
    @{ Name='evaluation'; Script='v2/scripts/evaluate.py'; Args=@() },
    @{ Name='cpu_export'; Script='v2/scripts/export_cpu.py'; Args=@() },
    @{ Name='runtime_cuda'; Script='v2/scripts/runtime_check.py'; Args=@('--device','cuda','--generation') },
    @{ Name='runtime_cpu'; Script='v2/scripts/runtime_check.py'; Args=@('--device','cpu') }
)
foreach ($stage in $stages) {
    ('Running ' + $stage.Name) | Set-Content -LiteralPath $pipelineStatus -Encoding utf8
    $stageArgs = @($stage.Script) + $stage.Args
    $stageProcess = Start-Process -FilePath $pythonExe -ArgumentList $stageArgs -WindowStyle Hidden -PassThru -Wait -RedirectStandardOutput (Join-Path $projectRoot ('v2/reports/' + $stage.Name + '_run.log')) -RedirectStandardError (Join-Path $projectRoot ('v2/reports/' + $stage.Name + '_stderr.log'))
    if ($stageProcess.ExitCode -ne 0) { ('FAILED ' + $stage.Name) | Set-Content -LiteralPath $pipelineStatus -Encoding utf8; throw ('Stage failed: ' + $stage.Name) }
}
'COMPLETE training evaluation CPU export and real-model runtime checks' | Set-Content -LiteralPath $pipelineStatus -Encoding utf8
