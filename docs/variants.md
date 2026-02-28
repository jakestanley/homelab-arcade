# Variants

Variant registry lives in `config.yaml` under the `variants` list. Each entry declares the UI
metadata, the portal mount path, and where the portal can check status.

This repo follows the imported multi-variant and API specifications:

- [imported/PATTERNS/multi-variant-service.md](/abs/path/c:/Users/mail/git/github.com/jakestanley/homelab-arcade/imported/PATTERNS/multi-variant-service.md)
- [imported/PATTERNS/api.md](/abs/path/c:/Users/mail/git/github.com/jakestanley/homelab-arcade/imported/PATTERNS/api.md)

That means variants are additive modules mounted under `/<variant>/`, shared portal and styling stay in core, and each variant owns its own status and API contract.

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
3) Implement `GET /health` and `GET /openapi.json` for the variant API.
4) Add a variant entry to `config.yaml`.
5) Use relative API paths (no leading `/`) in the UI so it works under the mount path.

Sandstorm example:

```yaml
variants:
  - id: sandstorm
    display_name: "Insurgency: Sandstorm"
    description: Start and stop the dedicated server
    port_key: sandstorm.sandstorm_web_port
    status_path: /api/status
    path: /sandstorm
```

Keep variant-specific configuration namespaced inside its section so it does not leak into core config. For example, Sandstorm uses keys such as `sandstorm.sandstorm_path` and `sandstorm.sandstorm_web_port`.
