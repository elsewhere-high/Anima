param([Parameter(ValueFromRemainingArguments=$true)][object[]]$ExtraArgs)
& (Join-Path $PSScriptRoot 'v5/start.ps1') -Device cpu @ExtraArgs
exit $LASTEXITCODE
