# AWS Log Searcher

Company desktop tool for searching AWS CloudWatch logs across multiple log groups (QA / SB / PROD).

**Stack:** Python 3 + PyQt6 + `awslogs` CLI (local AWS profiles).

## Requirements

- Python 3.10+
- AWS CLI profiles configured (`aws configure` or `aws sso login`)
- `awslogs` on PATH (`pip install awslogs`)

## Quick start

```bash
cd awslogs-w-gui
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Optional iTerm alias:

```bash
alias logsearch="cd /path/to/awslogs-w-gui && source .venv/bin/activate && python main.py"
```

## Configuration

| File | In git? | Purpose |
|------|---------|---------|
| `config.company.json.example` | yes | Template — copy to `config.company.json` |
| `config.company.json` | **no** (gitignored) | Your env → log group paths + AWS profiles |
| `config.local.json.example` | yes | Template for personal prefs |
| `config.local.json` | **no** (gitignored) | Preferences / personal overrides |

### First-time setup (other people)

1. `cp config.company.json.example config.company.json`
2. Edit `config.company.json`: put your CloudWatch log group paths and AWS profile names
3. Or skip the file and fill **Settings → Preferences → Paths & Profiles** in the UI (saved to `config.local.json`)
4. `aws sso login` / `aws configure` for those profiles
5. `python main.py`

**Profile resolution:** for each path, the app picks the longest `profiles` key that is a substring of the path.

See [app/config/schema.md](app/config/schema.md).

### Preferences UI (keep it simple)

| Section | What it does |
|---------|----------------|
| **General** | Highlight, sort-on-finish, beautify JSON, collapse long logs, keep-awake (off by default) |
| **Paths & Profiles** | Per-env log groups + `pathSubstring=awsProfile` lines |
| **Shortcuts** | Click a field, press keys (e.g. ⌘T) — auto-captured |

## Features (v2)

- Multi-tab searches with virtualized result list (handles large result sets)
- Parallel `awslogs get` across selected log groups
- Path multi-select, client-side filter, detail pane with JSON pretty-print
- Clear auth / rate-limit / missing-group errors
- Preferences saved to `config.local.json`
- Optional macOS keep-awake (**off by default**)

### Shortcuts (defaults)

| Action | macOS | Windows/Linux |
|--------|-------|---------------|
| New tab | ⌘T | Ctrl+T |
| Close tab | ⌘W | Ctrl+W |
| Search selection in new tab | ⌘D | Ctrl+D |
| Stop search | ⌘⇧S | Ctrl+Shift+S |
| Copy full log | ⌘⇧C | Ctrl+Shift+C |
| Copy awslogs command | ⌘⇧A | Ctrl+Shift+A |

Customize under **Settings → Preferences**.

## macOS app build

```bash
chmod +x packaging/build_macos.sh
./packaging/build_macos.sh
```

Output: `packaging/dist/AWS Log Searcher.app`

End users still need AWS credentials / SSO and `awslogs` available in their environment.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `awslogs` not found | `pip install awslogs` (same venv or global) |
| ExpiredToken / credentials | `aws sso login --profile <name>` |
| AccessDenied | Check IAM permissions for CloudWatch Logs on that profile |
| Log group not found | Verify path in `config.company.json` / Preferences |
| Empty results | Widen start time; confirm filter text matches CloudWatch filter pattern rules |

Debug logging:

```bash
LOG_LEVEL=DEBUG python main.py
```

## Smoke checklist

- [ ] Search across multiple groups returns rows
- [ ] Stop cancels in-flight work
- [ ] Client filter narrows the list without re-querying AWS
- [ ] Export writes a text file
- [ ] Preferences save and reload via `config.local.json`
- [ ] Wrong profile shows a readable credentials error

## Legacy

Previous Tkinter implementation lives under [`legacy/`](legacy/) for reference only. Do not use it for new work.

## Roadmap

See [docs/ROADMAP.md](docs/ROADMAP.md) for multi-team / platform plans.
