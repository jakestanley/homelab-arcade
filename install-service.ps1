param(
    [string]$ServiceName = "arcade",
    [string]$RepoPath = $PSScriptRoot,
    [string]$PythonExe,
    [pscredential]$Credential,
    [switch]$Start
)

$script = Join-Path $PSScriptRoot "scripts\\install-service.ps1"
if (-not (Test-Path -Path $script)) {
    throw "Missing scripts/install-service.ps1 at $script"
}

& $script -ServiceName $ServiceName -RepoPath $RepoPath -PythonExe $PythonExe -Credential $Credential -Start:$Start
