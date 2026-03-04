# Recovery

## Prerequisites

Recover this service onto a Linux host with:

- `systemd` available and functional
- the packaged `homelab-arcade` executable restored to a stable absolute path
- a dedicated `arcade` user and group
- a Python 3 runtime and installed dependencies from [`requirements.txt`](/Users/jake/git/github.com/jakestanley/homelab-arcade/requirements.txt) or [`pyproject.toml`](/Users/jake/git/github.com/jakestanley/homelab-arcade/pyproject.toml)
- host-specific config restored from [`config.example.yaml`](/Users/jake/git/github.com/jakestanley/homelab-arcade/config.example.yaml)

Quick checks:

```sh
getent passwd arcade >/dev/null
getent group arcade >/dev/null
systemctl --version && systemd-analyze --version
test -x /usr/local/bin/homelab-arcade
python3 -c "import flask, yaml, rcon"
```

## Service User And Files

Recommended Linux host locations:

- service user/group: `arcade:arcade`
- installed executable: `/usr/local/bin/homelab-arcade`
- unit file: `/etc/systemd/system/arcade.service`
- host env file: `/etc/arcade/arcade.env`
- host config file: `/etc/arcade/config.yaml`
- writable state directory: `/var/lib/homelab-arcade`

Repo-owned systemd assets:

- [`systemd/arcade.service`](/Users/jake/git/github.com/jakestanley/homelab-arcade/systemd/arcade.service)
- [`systemd/arcade.env.example`](/Users/jake/git/github.com/jakestanley/homelab-arcade/systemd/arcade.env.example)

There is no repo-owned Linux log directory to restore. Journald is the default log sink. Game installs and their writable state remain wherever `CS2_PATH` and `SANDSTORM_PATH` point.

Ensure `/etc/arcade/config.yaml` is readable by `arcade:arcade`. The env file may stay root-owned because `systemd` reads it before dropping privileges.

## Restore Order

1. Restore or reinstall the packaged `homelab-arcade` executable.
2. Restore the Python runtime dependencies if they are managed separately on the host.
3. Restore `/etc/arcade/arcade.env`.
4. Restore `/etc/arcade/config.yaml` and verify `HOMELAB_ARCADE_CONFIG_PATH` points to it.
5. Install or restore `/etc/systemd/system/arcade.service`.
6. Restore any external game binaries, save data, or configs referenced by `CS2_PATH` and `SANDSTORM_PATH`.

## Start And Verify

Reload and start the service:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now arcade.service
```

Verify runtime health:

```sh
systemctl status arcade.service
journalctl -u arcade.service -n 100 --no-pager
curl -fsS http://127.0.0.1:${PORTAL_PORT:-80}/api/variants
```

If the portal is up but a game runner fails, check host-specific executable paths in `/etc/arcade/config.yaml`. The bundled example values are Windows-oriented and may need Linux-specific replacements during recovery.
