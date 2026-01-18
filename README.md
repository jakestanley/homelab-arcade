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

## Notes

- The server assumes CS2 is already installed at `CS2_PATH`.
- Default mode/map: competitive on de_dust2 (override via `.env`).
- The web UI can send RCON commands, including a custom command input.
