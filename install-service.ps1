param(
    [string]$ServiceName = "CS2ControlDeck",
    [string]$RepoPath = $PSScriptRoot,
    [string]$VenvPath = ".venv",
    [pscredential]$Credential,
    [switch]$Start
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Get-Command nssm -ErrorAction SilentlyContinue)) {
    throw "nssm not found on PATH. Install NSSM and try again."
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

$repoFull = (Resolve-Path -Path $RepoPath).Path
$py = Join-Path $repoFull (Join-Path $VenvPath "Scripts\python.exe")
$server = Join-Path $repoFull "server.py"
$logsDir = Join-Path $repoFull "logs"

if (-not (Test-Path -Path $py)) {
    throw "Python venv not found at $py"
}
if (-not (Test-Path -Path $server)) {
    throw "server.py not found at $server"
}
if (-not (Test-Path -Path $logsDir)) {
    New-Item -ItemType Directory -Path $logsDir | Out-Null
}

$serviceExists = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if (-not $serviceExists) {
    nssm install $ServiceName $py $server
}
nssm set $ServiceName AppDirectory $repoFull
nssm set $ServiceName AppStdout (Join-Path $logsDir "cs2-control-deck.out.log")
nssm set $ServiceName AppStderr (Join-Path $logsDir "cs2-control-deck.err.log")
nssm set $ServiceName AppRotateFiles 1
nssm set $ServiceName AppRotateOnline 1
nssm set $ServiceName AppRotateSeconds 86400

$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Credential.Password)
try {
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}
nssm set $ServiceName ObjectName $Credential.UserName $plain

if ($Start) {
    if ((Get-Service -Name $ServiceName -ErrorAction SilentlyContinue).Status -eq "Running") {
        nssm stop $ServiceName
    }
    nssm start $ServiceName
}
