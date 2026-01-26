# Variants

Variant registry lives in `config.yaml` under the `variants` list. Each entry declares the UI
metadata and where the portal can check status.

Required fields:

- `id`: stable identifier
- `display_name`: user-facing label
- `port_env` or `port`: either the environment variable that contains the port, or a fixed port
- `status_path`: endpoint that returns `{running, ready}` (defaults to `/api/status` if omitted)
- `ui_path`: UI root path (defaults to `/` if omitted)

Optional fields:

- `description`: short card text

Example:

```yaml
variants:
  - id: cs2
    display_name: Counter-Strike 2
    description: Primary control UI
    port_env: WEB_PORT
    status_path: /api/status
    ui_path: /
```

When adding a new variant:

1) Ensure the server binds to its configured port.
2) Implement `/api/status` to return `{running: bool, ready: bool}`.
3) Add a variant entry to `config.yaml`.
