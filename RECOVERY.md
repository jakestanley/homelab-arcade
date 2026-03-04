# Recovery

## Prerequisites

Recover this service onto a Linux host with:

- `systemd` available and functional
- a checkout of this repo restored to `/srv/arcade` or another stable path
- a dedicated `arcade` user and group
- a Python 3 interpreter and installed dependencies from [`requirements.txt`](/Users/jake/git/github.com/jakestanley/homelab-arcade/requirements.txt)
- host-specific config restored from [`config.example.yaml`](/Users/jake/git/github.com/jakestanley/homelab-arcade/config.example.yaml)

Quick checks:

```sh
getent passwd arcade >/dev/null
getent group arcade >/dev/null
systemctl --version && systemd-analyze --version
test -x /srv/arcade/.venv/bin/python3
/srv/arcade/.venv/bin/python3 -c "import flask, yaml, rcon"
```

## Service User And Files

Recommended Linux host locations:

- service user/group: `arcade:arcade`
- repo checkout: `/srv/arcade`
- unit file: `/etc/systemd/system/arcade.service`
- host env file: `/etc/arcade/arcade.env`
- host config file: `/etc/arcade/config.yaml`

Repo-owned systemd assets:

- [`systemd/arcade.service`](/Users/jake/git/github.com/jakestanley/homelab-arcade/systemd/arcade.service)
- [`systemd/arcade.env.example`](/Users/jake/git/github.com/jakestanley/homelab-arcade/systemd/arcade.env.example)
- [`scripts/up.sh`](/Users/jake/git/github.com/jakestanley/homelab-arcade/scripts/up.sh)

There is no repo-owned Linux log directory to restore. Journald is the default log sink. Game installs and their writable state remain wherever `CS2_PATH` and `SANDSTORM_PATH` point.

Ensure `/srv/arcade` and `/etc/arcade/config.yaml` are readable by `arcade:arcade`. The env file may stay root-owned because `systemd` reads it before dropping privileges.

## Restore Order

1. Restore the repo files to `/srv/arcade`.
2. Restore or recreate the Python environment and reinstall dependencies.
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
curl -fsS http://127.0.0.1:${PORTAL_PORT:-80}/health
```

If the portal is up but a game runner fails, check host-specific executable paths in `/etc/arcade/config.yaml`. The bundled example values are Windows-oriented and may need Linux-specific replacements during recovery.
