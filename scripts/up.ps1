param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$PythonExe,
    [string]$RegistryServiceName = "arcade",
    [switch]$SkipPreflight
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-PythonExe {
    param([string]$RepoRoot, [string]$PythonExe)

    if ($PythonExe) {
        return (Resolve-Path -Path $PythonExe).Path
    }

    $envPython = $env:HOMELAB_ARCADE_PYTHON_EXE
    if ($envPython) {
        return (Resolve-Path -Path $envPython).Path
    }

    $venvPython = Join-Path $RepoRoot ".venv\\Scripts\\python.exe"
    if (Test-Path -Path $venvPython) {
        return $venvPython
    }

    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    throw "Python executable not found. Provide -PythonExe or set HOMELAB_ARCADE_PYTHON_EXE."
}

function Get-RepoName {
    param([string]$RepoRoot)
    return Split-Path -Leaf $RepoRoot
}

function Resolve-RepoPath {
    param([string]$EnvVar, [string]$Fallback)
    $value = [Environment]::GetEnvironmentVariable($EnvVar)
    if ($value) {
        return $value
    }
    if ($Fallback -and (Test-Path -Path $Fallback)) {
        return (Resolve-Path -Path $Fallback).Path
    }
    return $null
}

function Resolve-InfraPath {
    param([string]$RepoRoot)
    $parent = Split-Path -Parent $RepoRoot
    return Resolve-RepoPath -EnvVar "HOMELAB_INFRA_PATH" -Fallback (Join-Path $parent "homelab-infra")
}

function Test-GitRepo {
    param([string]$Path, [string]$Name)
    if (-not $Path) {
        return @("$Name path not configured.")
    }
    if (-not (Test-Path -Path $Path)) {
        return @("$Name not found at $Path.")
    }

    $git = Get-Command git -ErrorAction SilentlyContinue
    if (-not $git) {
        return @("git not found; cannot verify $Name status.")
    }

    $issues = @()
    $inside = & $git.Source -C $Path rev-parse --is-inside-work-tree 2>$null
    if ($LASTEXITCODE -ne 0 -or $inside -ne "true") {
        $issues += "$Name is not a git repository."
        return $issues
    }

    $status = & $git.Source -C $Path status --porcelain
    if ($status) {
        $issues += "$Name has uncommitted changes."
    }

    $branch = & $git.Source -C $Path rev-parse --abbrev-ref HEAD
    if ($branch -and ($branch -ne "main") -and ($branch -ne "master")) {
        $issues += "$Name is on branch '$branch' (expected main/master)."
    }

    return $issues
}

function Invoke-Preflight {
    param([string]$RepoRoot, [switch]$SkipPreflight)

    if ($SkipPreflight) {
        return
    }

    $infraPath = Resolve-InfraPath -RepoRoot $RepoRoot
    $parent = Split-Path -Parent $RepoRoot
    $standardsPath = Resolve-RepoPath -EnvVar "HOMELAB_STANDARDS_PATH" -Fallback (Join-Path $parent "homelab-standards")

    $issues = @()
    $issues += Test-GitRepo -Path $infraPath -Name "homelab-infra"
    $issues += Test-GitRepo -Path $standardsPath -Name "homelab-standards"

    $issues = $issues | Where-Object { $_ }
    if (-not $issues) {
        return
    }

    foreach ($issue in $issues) {
        Write-Warning $issue
    }

    if ($Host.Name -eq "ConsoleHost") {
        $response = Read-Host "Preflight warnings detected. Continue? (y/N)"
        if ($response -notin @("y", "Y")) {
            throw "Aborted due to preflight warnings."
        }
    }
}

function Get-ConfigPorts {
    param([string]$PythonExe, [string]$RepoRoot)

    $configPath = Join-Path $RepoRoot "config.yaml"
    $script = @"
import json
import os
from pathlib import Path

def coerce_port(value):
    try:
        port = int(value)
    except (TypeError, ValueError):
        return None
    return port if port > 0 else None

ports = set()

config_path = Path(r"$configPath")
data = {}
if config_path.exists():
    raw = config_path.read_text(encoding="utf-8")
    if raw.strip():
        try:
            import yaml
        except Exception:
            yaml = None
        if yaml:
            parsed = yaml.safe_load(raw) or {}
            if isinstance(parsed, dict):
                data = parsed

def add_port(value):
    port = coerce_port(value)
    if port:
        ports.add(port)

add_port(data.get("portal_port") if isinstance(data, dict) else None)
add_port(os.environ.get("PORTAL_PORT"))

print(json.dumps(sorted(ports)))
"@

    $portsJson = $script | & $PythonExe -
    if (-not $portsJson) {
        return @()
    }

    try {
        return ($portsJson | ConvertFrom-Json)
    } catch {
        return @()
    }
}

function Get-RegistryPort {
    param([string]$PythonExe, [string]$RegistryPath, [string]$ServiceName)

    if (-not (Test-Path -Path $RegistryPath)) {
        return $null
    }

    $script = @"
import json
from pathlib import Path

service_name = r"$ServiceName"
registry_path = Path(r"$RegistryPath")
data = {}
if registry_path.exists():
    raw = registry_path.read_text(encoding="utf-8")
    if raw.strip():
        try:
            import yaml
        except Exception:
            yaml = None
        if yaml:
            parsed = yaml.safe_load(raw) or {}
            if isinstance(parsed, dict):
                data = parsed

services = data.get("services") if isinstance(data, dict) else None
port = None
if isinstance(services, dict):
    service = services.get(service_name)
    if isinstance(service, dict):
        upstream = service.get("upstream")
        if isinstance(upstream, dict):
            port = upstream.get("port")

try:
    port = int(port)
except (TypeError, ValueError):
    port = None

if port and port > 0:
    print(port)
"@

    $value = $script | & $PythonExe -
    if (-not $value) {
        return $null
    }

    try {
        return [int]$value
    } catch {
        return $null
    }
}

function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Ensure-FirewallRule {
    param([string]$RuleName, [int]$Port)

    $existing = Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue
    if ($existing) {
        $filters = $existing | Get-NetFirewallPortFilter
        foreach ($filter in $filters) {
            if ($filter.Protocol -eq "TCP" -and $filter.LocalPort -eq "$Port") {
                return
            }
        }
    }

    if (Test-Admin) {
        New-NetFirewallRule -DisplayName $RuleName -Direction Inbound -Protocol TCP -LocalPort $Port -Action Allow -Profile Private | Out-Null
        return
    }

    Write-Warning ("Firewall rule missing for port {0}. Run elevated: New-NetFirewallRule -DisplayName ""{1}"" -Direction Inbound -Protocol TCP -LocalPort {0} -Action Allow -Profile Private" -f $Port, $RuleName)
}

function Ensure-FirewallRules {
    param([string]$RepoRoot, [string[]]$Ports)

    if (-not $Ports) {
        return
    }

    $repoName = Get-RepoName -RepoRoot $RepoRoot
    foreach ($port in $Ports) {
        if (-not $port) {
            continue
        }
        $ruleName = "$repoName Port $port"
        Ensure-FirewallRule -RuleName $ruleName -Port ([int]$port)
    }
}

Invoke-Preflight -RepoRoot $RepoRoot -SkipPreflight:$SkipPreflight

$python = Resolve-PythonExe -RepoRoot $RepoRoot -PythonExe $PythonExe
$venvPath = Join-Path $RepoRoot ".venv"
if (-not (Test-Path -Path $venvPath)) {
    & $python -m venv $venvPath
}

$venvPython = Join-Path $venvPath "Scripts\\python.exe"
if (-not (Test-Path -Path $venvPython)) {
    throw "Virtual environment Python not found at $venvPython"
}

$requirements = Join-Path $RepoRoot "requirements.txt"
if (-not (Test-Path -Path $requirements)) {
    throw "requirements.txt not found at $requirements"
}

& $venvPython -m pip install -r $requirements

$infraPath = Resolve-InfraPath -RepoRoot $RepoRoot
$registryPath = if ($infraPath) { Join-Path $infraPath "registry.yaml" } else { $null }
$registryPort = if ($registryPath) { Get-RegistryPort -PythonExe $venvPython -RegistryPath $registryPath -ServiceName $RegistryServiceName } else { $null }
if ($registryPort) {
    $env:PORTAL_PORT = $registryPort
} else {
    Write-Warning "Unable to resolve PORTAL_PORT from homelab-infra registry.yaml."
}

$ports = Get-ConfigPorts -PythonExe $venvPython -RepoRoot $RepoRoot
Ensure-FirewallRules -RepoRoot $RepoRoot -Ports $ports

$supervisor = Join-Path $RepoRoot "supervisor.py"
if (-not (Test-Path -Path $supervisor)) {
    throw "Supervisor not found at $supervisor"
}

& $venvPython $supervisor
