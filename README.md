# Homelab Arcade

Homelab Arcade runs a small portal plus game control UIs from one supervisor process. The portal is the public entrypoint for the service; ingress, DNS, and exposed ports are owned by `homelab-infra` and must not be configured in this repo.

This repo supports three operational shapes:

- packaged Linux service via the installed `homelab-arcade` executable
- generic mutable-host/manual runs from a repo checkout
- Windows host service via NSSM and `scripts/up.ps1`

For packaging-oriented Linux hosts, the long-running contract is the installed `homelab-arcade` console script, which dispatches `supervisor:main`. Host-specific env and YAML config stay external, and game installs remain host-managed outside the package.

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

Host-local game install paths remain external. Keep values such as `CS2_PATH` and `SANDSTORM_PATH` in `/etc/arcade/config.yaml`, an environment file, or another host-managed config source; the package does not install the actual games.

## Dependencies

Required host dependencies:

- `systemd` for Linux service supervision
- A Python 3 interpreter compatible with the installed package
- Runtime Python dependencies from [`requirements.txt`](/Users/jake/git/github.com/jakestanley/homelab-arcade/requirements.txt) or the equivalent package metadata in [`pyproject.toml`](/Users/jake/git/github.com/jakestanley/homelab-arcade/pyproject.toml)

Verification commands:

```sh
systemctl --version && systemd-analyze --version
test -x /usr/local/bin/homelab-arcade
python3 -c "import flask, yaml, rcon"
```

Optional desktop helper dependency:

- `pyqt6` is not required for the headless web supervisor path.
- If you still use the legacy local CS2 desktop helper, install the package with the `desktop` extra.

## Linux systemd

Packaged service contract:

- installed executable: `homelab-arcade`
- repo-owned unit template: [`systemd/arcade.service`](/Users/jake/git/github.com/jakestanley/homelab-arcade/systemd/arcade.service)
- host env template: [`systemd/arcade.env.example`](/Users/jake/git/github.com/jakestanley/homelab-arcade/systemd/arcade.env.example)

Recommended host file locations for package-oriented installs:

- installed executable: `/usr/local/bin/homelab-arcade` or another absolute package-managed path
- Unit install path: `/etc/systemd/system/arcade.service`
- Host env file: `/etc/arcade/arcade.env`
- Host config file: `/etc/arcade/config.yaml`
- Writable working/state directory: `/var/lib/homelab-arcade`

Suggested setup:

```sh
sudo useradd --system --home /var/lib/homelab-arcade --shell /usr/sbin/nologin arcade
sudo install -d -o root -g arcade -m 0750 /etc/arcade
sudo install -d -o arcade -g arcade /var/lib/homelab-arcade
sudo install -m 0644 /path/to/homelab-arcade/systemd/arcade.service /etc/systemd/system/arcade.service
sudo install -o root -g arcade -m 0640 /path/to/homelab-arcade/systemd/arcade.env.example /etc/arcade/arcade.env
sudo install -o arcade -g arcade -m 0640 /path/to/homelab-arcade/config.example.yaml /etc/arcade/config.yaml
```

Then edit `/etc/arcade/arcade.env` and set at minimum:

```sh
HOMELAB_ARCADE_CONFIG_PATH=/etc/arcade/config.yaml
PORTAL_PORT=<host-assigned or infra-assigned value>
```

The unit template assumes the executable is available at `/usr/local/bin/homelab-arcade`. If your package manager installs it elsewhere, change `ExecStart=` to that absolute path. Declarative NixOS units typically bypass the checked-in unit template and point directly at the package output path.

Enable and start:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now arcade.service
```

View logs:

```sh
journalctl -u arcade.service -f
```

## Generic Manual Linux Host

The mutable-host/manual bridge still exists, but it is no longer the preferred packaging contract.

Canonical wrapper for repo-checkout runs:

- [`scripts/up.sh`](/Users/jake/git/github.com/jakestanley/homelab-arcade/scripts/up.sh)

Typical manual setup:

```sh
python3 -m pip install .
HOMELAB_ARCADE_CONFIG_PATH=/etc/arcade/config.yaml homelab-arcade
```

If you explicitly want to run from a checkout instead of an installed package:

```sh
ARCADE_PYTHON=/srv/arcade/.venv/bin/python3 HOMELAB_ARCADE_CONFIG_PATH=/etc/arcade/config.yaml /path/to/homelab-arcade/scripts/up.sh
```

## Windows NSSM

Windows remains the existing primary runtime for the bundled CS2 and Sandstorm examples.

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# install optional desktop helper deps only if you need the PyQt CS2 tool
# pip install ".[desktop]"
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
