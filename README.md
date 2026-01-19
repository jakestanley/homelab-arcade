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
python server.py
```

Open `http://localhost:5000` (or `WEB_PORT` if changed).

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

- The server loads `.env` from the repo root automatically.
- The installer will prompt for credentials so the service runs as your user. For local users, use `.\Username` or `COMPUTERNAME\Username`.
- Create the `logs` folder if you want log files (NSSM will not create it).
- Reinstall only if you change the venv path, script path, or NSSM config.

## Notes

- The server assumes CS2 is already installed at `CS2_PATH`.
- Default mode/map: competitive on de_dust2 (override via `.env`).
- The web UI can send RCON commands, including a custom command input.
