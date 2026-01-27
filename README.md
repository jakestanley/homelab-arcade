# CS2 Control Deck

Self-contained CS2 server manager with a web UI for starting/stopping, RCON actions, and map/mode changes.
Runtime is Windows + NSSM (no Docker); ingress and ports are defined by `homelab-infra/registry.yaml` (service name: `arcade`).

## Setup

1) Create and activate a virtual environment (Windows)

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

2) Install dependencies

```bash
pip install -r requirements.txt
```

3) Configure environment

```bash
copy config.example.yaml config.yaml
```

Edit `config.yaml` and set `cs2.cs2_path` and `cs2.rcon_password` at minimum. If your path has spaces, wrap it in quotes (see `config.example.yaml`). Ports and ingress are owned by `homelab-infra/registry.yaml`, so ensure `portal_port` matches the registry; variant upstream ports (`dummy_port`, `cs2.web_port`) are internal. Variant metadata lives in the `variants` list.

Optional: set environment variables in your shell (or copy `.env.example` to `.env` and load it yourself) to override config values.
`scripts/up.ps1` will auto-resolve `PORTAL_PORT` from `../homelab-infra/registry.yaml` for the `arcade` service.

## Run

Windows (recommended entrypoint):

```powershell
.\scripts\up.ps1
```

```bash
python supervisor.py
```

Open `http://<host>:<portal_port>` for the portal, or `http://<host>:<portal_port>/cs2/` for the CS2 UI.
On Windows, ports below 1024 require Administrator privileges.

## LAN access (Windows)

The portal and UIs listen on all interfaces by default. If LAN clients cannot connect, allow inbound TCP for the portal port in Windows Firewall. Running `.\scripts\up.ps1` elevated will create the rule; non-elevated runs will print the exact `New-NetFirewallRule` command.

## Multiple servers

This repo includes simple additional servers and a portal page. The portal is served on `portal_port` and proxies each game UI under a subpath.

- `portal_server.py` serves the index at `http://<host>:<portal_port>`
- `cs2/server.py` is proxied at `http://<host>:<portal_port>/cs2/`
- `dummy_server.py` is proxied at `http://<host>:<portal_port>/dummy/`

The portal and dummy pages reuse shared styles from `web/shared.css`. Variant registration is explicit in `config.yaml` under `variants`; see `docs/variants.md`.
The CS2 server and its assets live under `cs2/`.
Config files (`config.yaml`, `config.example.yaml`, `.env`, `.env.example`, `requirements.txt`) remain at repo root.

Portal notes:

- Links are LAN-safe and remain under the portal host/port using subpaths.
- Each game card shows a status pill via `/api/status` for each variant.

## Run as a Windows service (NSSM)

Assumes NSSM is installed and on PATH. `scripts/up.ps1` will create `.venv` on first run.

PowerShell (run as Administrator):

```powershell
.\scripts\install-service.ps1 -Start
```

Start/stop/status:

```powershell
nssm start arcade
nssm stop arcade
nssm status arcade
```

Restart after code changes:

```powershell
nssm restart arcade
```

Install script options:

```powershell
.\scripts\install-service.ps1 -ServiceName "arcade" -RepoPath "c:\path\to\homelab-arcade" -PythonExe "C:\Path\To\python.exe" -Start
```

Remove the service:

```powershell
nssm remove arcade confirm
```

Notes:

- The installer runs the supervisor, which starts the portal, CS2 UI, and dummy server together.
- The CS2 server loads `config.yaml` automatically.
- `SERVER_IP` is no longer used; the CS2 server auto-detects the host IP.
- The installer will prompt for credentials so the service runs as your user. For local users, use `.\Username` or `COMPUTERNAME\Username`.
- `scripts/install-service.ps1` defaults `ServiceName` to the repo folder name; the root `install-service.ps1` wrapper defaults `ServiceName=arcade`.
- Log files are written to `logs/` (created automatically).
- Reinstall only if you change the repo path, script path, or NSSM config.

## Notes

- The server assumes CS2 is already installed at `CS2_PATH`.
- Default mode/map: competitive on de_dust2 (override via `config.yaml`).
- The web UI can send RCON commands, including a custom command input.
