param([switch]$NoBrowser)
$ErrorActionPreference='Stop'
$demoUrl='http://127.0.0.1:8768'
function Get-DemoHealth {
    try { return Invoke-RestMethod -Uri "$demoUrl/health" -TimeoutSec 3 } catch { return $null }
}
$health=Get-DemoHealth
if (-not $health) {
    Write-Host 'Starting the local GPU service. The first load may take 1-2 minutes...'
    & (Join-Path $PSScriptRoot 'start_background.ps1')
    $deadline=(Get-Date).AddSeconds(150)
    do {
        Start-Sleep -Seconds 2
        $health=Get-DemoHealth
    } until ($health -or (Get-Date) -gt $deadline)
}
if (-not $health -or $health.status -ne 'ready' -or $health.version -ne '5.0.0') {
    throw 'V5 is not ready. Inspect v5/reports/server_stderr.log. Do not start duplicate services.'
}
Write-Host "Ready: $demoUrl"
if (-not $NoBrowser) {
    $edgePath=Join-Path ${env:ProgramFiles(x86)} 'Microsoft/Edge/Application/msedge.exe'
    if (Test-Path -LiteralPath $edgePath) {
        Start-Process -FilePath $edgePath -ArgumentList $demoUrl
    } else {
        Start-Process $demoUrl
    }
}
