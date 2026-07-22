# Dev / debug scratch scripts

One-off investigation scripts. Not part of the publish pipeline.

Run from repo root:

```powershell
uv run python scripts/dev/debug_team_total.py
uv run python scripts/dev/debug_remote.py --help
```

| Script | Purpose |
|--------|---------|
| `debug_team_total.py` | Inspect relational CSV joins for team totals |
| `check_team_total.py` | Quick bowling_ergebnisse CSV sanity check |
| `debug_remote.py` | Hit remote Flask API endpoints (edit `base_url` first) |
| `playground.py` | Ad-hoc scratch |

Local env bootstrap: [`../setup_dev_env.ps1`](../setup_dev_env.ps1) (`uv sync`).
