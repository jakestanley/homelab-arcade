param(
    [string]$ServiceName,
    [string]$RepoPath = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$PythonExe,
    [pscredential]$Credential,
    [switch]$Start
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Get-Command nssm -ErrorAction SilentlyContinue)) {
    throw "nssm not found on PATH. Install NSSM and try again."
}

$repoFull = (Resolve-Path -Path $RepoPath).Path
if (-not $ServiceName) {
    $ServiceName = Split-Path -Leaf $repoFull
}

$upScript = Join-Path $repoFull "scripts\\up.ps1"
if (-not (Test-Path -Path $upScript)) {
    throw "up.ps1 not found at $upScript"
}

$logsDir = Join-Path $repoFull "logs"
if (-not (Test-Path -Path $logsDir)) {
    New-Item -ItemType Directory -Path $logsDir | Out-Null
}
$logPrefix = Split-Path -Leaf $repoFull

$psExe = (Get-Command powershell -ErrorAction SilentlyContinue).Source
if (-not $psExe) {
    $psExe = "powershell.exe"
}

$appParams = "-NoProfile -ExecutionPolicy Bypass -File `"$upScript`" -RepoRoot `"$repoFull`" -SkipPreflight"

$serviceExists = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if (-not $serviceExists) {
    nssm install $ServiceName $psExe
}

nssm set $ServiceName Application $psExe
nssm set $ServiceName AppParameters $appParams
nssm set $ServiceName AppDirectory $repoFull
nssm set $ServiceName AppStdout (Join-Path $logsDir "$logPrefix.out.log")
nssm set $ServiceName AppStderr (Join-Path $logsDir "$logPrefix.err.log")
nssm set $ServiceName AppRotateFiles 1
nssm set $ServiceName AppRotateOnline 1
nssm set $ServiceName AppRotateSeconds 86400

if ($PythonExe) {
    nssm set $ServiceName AppEnvironmentExtra "HOMELAB_ARCADE_PYTHON_EXE=$PythonExe"
}

$domain = $env:USERDOMAIN
if (-not $domain -or $domain -eq "WORKGROUP") {
    $domain = $env:COMPUTERNAME
}
$defaultUser = if ($domain) { "$domain\$env:USERNAME" } else { $env:USERNAME }
if (-not $Credential) {
    $Credential = Get-Credential -UserName $defaultUser -Message "Credentials for NSSM service logon"
}
if (-not $Credential) {
    throw "No credentials provided."
}

$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Credential.Password)
try {
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}
nssm set $ServiceName ObjectName $Credential.UserName $plain

if ($Start) {
    $status = (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue).Status
    if ($status -and $status -ne "Stopped") {
        nssm restart $ServiceName
    } else {
        nssm start $ServiceName
    }
}
