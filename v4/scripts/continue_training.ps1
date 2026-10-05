param([int]$StateTrainingPid)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
Set-Location -LiteralPath $projectRoot
$env:PYTHONUTF8 = '1'
if ($StateTrainingPid -gt 0 -and (Get-Process -Id $StateTrainingPid -ErrorAction SilentlyContinue)) {
    Wait-Process -Id $StateTrainingPid
}
if (-not (Test-Path -LiteralPath 'v4/runs/current_state_lora/selection.json')) {
    throw 'Current-state training did not complete; inspect its existing log. No automatic restart.'
}
$python = Join-Path $projectRoot '.venv_zh/Scripts/python.exe'
if (-not (Test-Path -LiteralPath 'v4/reports/current_state_evaluation.json')) {
    & $python v4/scripts/evaluate_current_state.py *> v4/reports/current_state_evaluation.log
    if ($LASTEXITCODE -ne 0) { throw 'State evaluation failed; inspect current_state_evaluation.log' }
}
if (-not (Test-Path -LiteralPath 'v4/runs/dialogue_sft/selection.json')) {
    & $python v4/scripts/train_dialogue.py *> v4/reports/dialogue_training.log
    if ($LASTEXITCODE -ne 0) { throw 'Dialogue training failed; inspect dialogue_training.log' }
}
if (-not (Test-Path -LiteralPath 'v4/reports/dialogue_evaluation.json')) {
    & $python v4/scripts/evaluate_dialogue.py *> v4/reports/dialogue_evaluation.log
    if ($LASTEXITCODE -ne 0) { throw 'Dialogue evaluation failed; inspect dialogue_evaluation.log' }
}
Write-Output 'Training and fixed evaluation finished. Manual response review and actual runtime verification remain.'
