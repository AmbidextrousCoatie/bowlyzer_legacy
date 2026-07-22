# Data pipeline scripts

Import adapters and extraction tools (moved from repo root and `database/input/`).

| Script | Purpose |
|--------|---------|
| `import_clubmeisterschaft_donaubowler_xlsx.py` | Clubpokal XLSX → staging CSV |
| `import_bayerische_meisterschaft_xlsx.py` | BM XLSX → GF regional merge |
| `convert_bowlingbayern_to_legacy.py` | Static liga CSV → legacy format |
| `extract_excel_data.py` | Historical Excel league extract |

Raw inputs live under `database/work/raw/`. Staging outputs under `database/work/tournaments/staging/`.
