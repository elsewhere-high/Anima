$ErrorActionPreference='Stop'
$record=Join-Path $PSScriptRoot 'v5/reports/server_process.json'
if (-not (Test-Path -LiteralPath $record)) { Write-Output 'No managed V5 server record.'; exit 0 }
$metadata=Get-Content -LiteralPath $record -Raw | ConvertFrom-Json
$rootProcess=Get-CimInstance Win32_Process -Filter "ProcessId = $($metadata.pid)"
if (-not $rootProcess) { Write-Output 'Managed V5 server already stopped.'; exit 0 }
if ($rootProcess.CommandLine -notlike '*social_v5.server:app*' -or $rootProcess.CommandLine -notlike "*$PSScriptRoot*") { throw 'Process identity did not match the managed V5 service.' }
$children=Get-CimInstance Win32_Process -Filter "ParentProcessId = $($metadata.pid)"
foreach ($child in $children) {
    if ($child.Name -eq 'conhost.exe') { continue }
    if ($child.CommandLine -notlike '*social_v5.server:app*') { throw "Unexpected child process $($child.ProcessId)" }
    Stop-Process -Id $child.ProcessId -ErrorAction SilentlyContinue
}
Stop-Process -Id $metadata.pid -ErrorAction SilentlyContinue
Write-Output 'Managed V5 service stopped.'
