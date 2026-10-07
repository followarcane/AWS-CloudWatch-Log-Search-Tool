# Config schema

## Files

| File | Purpose |
|------|---------|
| `config.company.json.example` | Template in git (placeholder paths) |
| `config.company.json` | Real catalog (gitignored) — paths + AWS profile map |
| `config.local.json` | Per-user overrides (gitignored). Preferences / extra paths / personal shortcuts |

Local overrides are deep-merged on top of company config.

## `env_configs`

```json
{
  "QA": {
    "paths": ["/aws/eks/.../service-a"],
    "profiles": {
      "steller": "steller-developer",
      "bahama": "bahama-developer"
    }
  }
}
```

Profile resolution: for each path, pick the **longest** `profiles` key that appears as a substring of the path. No account names are hardcoded in application code.

## `highlight_settings`

- `search_highlight` (bool)
- `filter_highlight` (bool)
- `sort_by_time` (bool)

## `app_settings`

- `keep_awake` (bool, default `false`) — macOS caffeinate + F15 idle nudge every 3–5 min while focused
- `max_collapsed_lines` (int, default `15`) — logs longer than this collapse behind ▶ expand
- `beautify_logs` (bool, default `true`) — JSON indent + wrap X- headers (never drops content)

## `shortcuts`

Qt-style sequences per platform:

```json
"new_tab": { "win": "Ctrl+T", "mac": "Meta+T" }
```

`copy_awslogs_command` copies the full shell-ready `awslogs get …` line for the log block under the cursor (right-click or shortcut).
