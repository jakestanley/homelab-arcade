# Variants

Variant registry lives in `config.yaml` under the `variants` list. Each entry declares the UI
metadata, the portal mount path, and where the portal can check status.

Required fields:

- `id`: stable identifier
- `display_name`: user-facing label
- `port_key`, `port_env`, or `port`: a config path (e.g. `cs2.web_port`), an environment variable, or a fixed upstream port
- `path`: portal mount path (e.g. `/cs2`)
- `status_path`: endpoint that returns `{running, ready}` (defaults to `/api/status` if omitted)

Optional fields:

- `description`: short card text

Example:

```yaml
variants:
  - id: cs2
    display_name: Counter-Strike 2
    description: Primary control UI
    port_key: cs2.web_port
    status_path: /api/status
    path: /cs2
```

When adding a new variant:

1) Ensure the server binds to its configured port (internal; proxied by the portal).
2) Implement `/api/status` to return `{running: bool, ready: bool}`.
3) Add a variant entry to `config.yaml`.
4) Use relative API paths (no leading `/`) in the UI so it works under the mount path.
