param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemainingArgs
)

$script = Join-Path $PSScriptRoot "scripts\\install-service.ps1"
if (-not (Test-Path -Path $script)) {
    throw "Missing scripts/install-service.ps1 at $script"
}

if (-not $RemainingArgs -or $RemainingArgs.Count -eq 0) {
    $RemainingArgs = @("-ServiceName", "arcade")
} elseif ($RemainingArgs -notcontains "-ServiceName") {
    $RemainingArgs = $RemainingArgs + @("-ServiceName", "arcade")
}

& $script @RemainingArgs
