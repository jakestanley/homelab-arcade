# CS2 Control Deck

Self-contained CS2 server manager with a web UI for starting/stopping, RCON actions, and map/mode changes.

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
copy .env.example .env
```

Edit `.env` and set `CS2_PATH` and `RCON_PASSWORD` at minimum. If your path has spaces, wrap it in quotes (see `.env.example`).

## Run

```bash
python supervisor.py
```

Open `http://localhost:80` for the portal, or `http://localhost:5000` for the CS2 UI.
On Windows, port 80 requires Administrator privileges.

## LAN access (Windows)

The portal and UIs listen on all interfaces by default. If LAN clients cannot connect, allow inbound TCP ports 80, 5000, and 5001 in Windows Firewall:

```powershell
New-NetFirewallRule -DisplayName "CS2 Portal 80" -Direction Inbound -Protocol TCP -LocalPort 80 -Action Allow
New-NetFirewallRule -DisplayName "CS2 UI 5000" -Direction Inbound -Protocol TCP -LocalPort 5000 -Action Allow
New-NetFirewallRule -DisplayName "Dummy UI 5001" -Direction Inbound -Protocol TCP -LocalPort 5001 -Action Allow
```

## Multiple servers

This repo includes simple additional servers and a portal page. The portal is served on port 80 and links to each game UI.

- `portal_server.py` serves the index at `http://localhost:80`
- `cs2/server.py` serves CS2 at `http://localhost:5000`
- `dummy_server.py` serves a dummy game UI at `http://localhost:5001`

The portal and dummy pages reuse shared styles from `web/shared.css`.
The CS2 server and its assets live under `cs2/`.
Config files (`.env`, `.env.example`, `requirements.txt`) remain at repo root.

## Run as a Windows service (NSSM)

Assumes NSSM is installed and on PATH, and the virtual environment lives at `.venv`.

PowerShell (run as Administrator):

```powershell
.\install-service.ps1
```

Start/stop/status:

```powershell
nssm start CS2ControlDeck
nssm stop CS2ControlDeck
nssm status CS2ControlDeck
```

Restart after code changes:

```powershell
nssm restart CS2ControlDeck
```

Install script options:

```powershell
.\install-service.ps1 -ServiceName "CS2ControlDeck" -RepoPath "c:\path\to\cs2" -VenvPath ".venv" -Start
```

Remove the service:

```powershell
nssm remove CS2ControlDeck confirm
```

Notes:

- The installer runs the supervisor, which starts the portal, CS2 UI, and dummy server together.
- The CS2 server loads `.env` automatically.
- The installer will prompt for credentials so the service runs as your user. For local users, use `.\Username` or `COMPUTERNAME\Username`.
- Create the `logs` folder if you want log files (NSSM will not create it).
- Reinstall only if you change the venv path, script path, or NSSM config.

## Notes

- The server assumes CS2 is already installed at `CS2_PATH`.
- Default mode/map: competitive on de_dust2 (override via `.env`).
- The web UI can send RCON commands, including a custom command input.
