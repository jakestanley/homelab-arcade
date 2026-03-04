# Homelab Arcade

Homelab Arcade runs a small portal plus game control UIs from one supervisor process. The portal is the public entrypoint for the service; ingress, DNS, and exposed ports are owned by `homelab-infra` and must not be configured in this repo.

This repo now supports two host runtime models:

- Windows host service via NSSM and `scripts/up.ps1`
- Generic Linux host service via `systemd` and `scripts/up.sh`

The Linux systemd path is intentionally simple and Nix-friendly: the long-running contract is `supervisor.py`, the unit uses an absolute `ExecStart=`, and host-specific config can live outside the checkout via `HOMELAB_ARCADE_CONFIG_PATH`.

## Runtime Model

The supervisor starts all repo-owned components together:

- `portal_server.py` on `PORTAL_PORT`
- `cs2/server.py` on `WEB_PORT`
- `sandstorm/server.py` on `SANDSTORM_WEB_PORT`
- `dummy_server.py` on `DUMMY_PORT`

The portal serves on port 80 by default and links to each variant UI by LAN-safe subpaths on the same host. External exposure, reverse proxying, and final port assignments are managed in `homelab-infra`, not here.

Variant command paths remain host-specific. The example `config.example.yaml` is Windows-oriented for CS2 and Sandstorm, so Linux hosts must provide Linux-appropriate executable paths if those runners are expected to work there.

## Configuration

Application config can come from either environment variables or YAML:

- Root env template for manual runs: [`.env.example`](/Users/jake/git/github.com/jakestanley/homelab-arcade/.env.example)
- Example structured config: [`config.example.yaml`](/Users/jake/git/github.com/jakestanley/homelab-arcade/config.example.yaml)
- Linux host env template for `systemd`: [`systemd/arcade.env.example`](/Users/jake/git/github.com/jakestanley/homelab-arcade/systemd/arcade.env.example)

`HOMELAB_ARCADE_CONFIG_PATH` is optional. If set, the service reads config from that path instead of repo-local `config.yaml`. That is the recommended Linux host shape so mutable config can live under `/etc/arcade/`.

## Dependencies

Required host dependencies:

- `systemd` for Linux service supervision
- A Python 3 interpreter at the path used by the launcher
- Python packages from [`requirements.txt`](/Users/jake/git/github.com/jakestanley/homelab-arcade/requirements.txt)

Verification commands:

```sh
systemctl --version && systemd-analyze --version
test -x /srv/arcade/.venv/bin/python3
/srv/arcade/.venv/bin/python3 -c "import flask, yaml, rcon"
```

For Windows NSSM deployments, continue using the existing PowerShell workflow documented below.

## Linux systemd

Canonical Linux entrypoint:

- [`scripts/up.sh`](/Users/jake/git/github.com/jakestanley/homelab-arcade/scripts/up.sh)

Repo-owned unit template:

- [`systemd/arcade.service`](/Users/jake/git/github.com/jakestanley/homelab-arcade/systemd/arcade.service)

Recommended host file locations:

- Repo checkout: `/srv/arcade`
- Unit install path: `/etc/systemd/system/arcade.service`
- Host env file: `/etc/arcade/arcade.env`
- Host config file: `/etc/arcade/config.yaml`

Suggested setup:

```sh
sudo useradd --system --home /srv/arcade --shell /usr/sbin/nologin arcade
sudo install -d -o arcade -g arcade /srv/arcade
sudo install -d -o root -g arcade -m 0750 /etc/arcade
sudo cp -R /path/to/homelab-arcade/. /srv/arcade/
sudo chown -R arcade:arcade /srv/arcade
sudo -u arcade python3 -m venv /srv/arcade/.venv
sudo -u arcade /srv/arcade/.venv/bin/pip install -r /srv/arcade/requirements.txt
sudo install -m 0644 /srv/arcade/systemd/arcade.service /etc/systemd/system/arcade.service
sudo install -o root -g arcade -m 0640 /srv/arcade/systemd/arcade.env.example /etc/arcade/arcade.env
sudo install -o arcade -g arcade -m 0640 /srv/arcade/config.example.yaml /etc/arcade/config.yaml
```

Then edit `/etc/arcade/arcade.env` and set at minimum:

```sh
ARCADE_PYTHON=/srv/arcade/.venv/bin/python3
HOMELAB_ARCADE_CONFIG_PATH=/etc/arcade/config.yaml
PORTAL_PORT=<value assigned by homelab-infra>
```

Enable and start:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now arcade.service
```

View logs:

```sh
journalctl -u arcade.service -f
```

Manual Linux start without `systemd`:

```sh
ARCADE_PYTHON=/srv/arcade/.venv/bin/python3 HOMELAB_ARCADE_CONFIG_PATH=/etc/arcade/config.yaml /srv/arcade/scripts/up.sh
```

## Windows NSSM

Windows remains the existing primary runtime for the bundled CS2 and Sandstorm examples.

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create `config.yaml` from [`config.example.yaml`](/Users/jake/git/github.com/jakestanley/homelab-arcade/config.example.yaml), then run:

```powershell
.\scripts\up.ps1
```

Install or update the NSSM service:

```powershell
.\scripts\install-service.ps1 -Start
```

The installer runs the supervisor so the portal and all variants stay under one Windows service, matching the repo constraint for `install-service.ps1`.

## Notes

- `SERVER_IP` is not required; CS2 auto-detects the host IP.
- The Linux unit writes logs to journald by default.
- This repo does not install firewall rules, reverse proxies, registry entries, or DNS for Linux hosts; that wiring belongs in `homelab-infra`.
