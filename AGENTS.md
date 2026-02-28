# Agents

## Vendored Standards

All behavioural. structural and configuration decisions must refer to vendored documentation under:
- `imported/`

## Repo Constraints (User-Provided)

- Keep a single `.env`, `.env.example`, and `requirements.txt` at repo root.
- All CS2-related files live under `cs2/` (API/server, CS2 web UI, maps/config/scripts, py module).
- `install-service.ps1` installs and runs all components as one service via `supervisor.py` (do not split into multiple services).
- Portal runs on port 80 and links to each game server UI; links must be LAN-safe (avoid `localhost`).
- CS2 server should auto-detect host IP for binding/RCON (no `SERVER_IP` in `.env`).
- Do not change existing CS2 server logic unless explicitly requested.
- Refer to `docs/variants.md`
