# Clubmeisterschaft Donaubowler — auto-import from Dropbox (VPS)

Ongoing tournament: **Clubmeisterschaft Donaubowler 2026**.  
Goal: while you are away, the VPS pulls the data owner’s Excel from Dropbox, runs the existing importer, and restarts the app so [bowlyzer.online](https://www.bowlyzer.online) shows fresh results.

**Clubpokal** (separate team KO over multiple months) is **not** this pipeline — it will get its own importer later.

**No manual “import on PC + deploy -SyncDatabase” during vacation** — set this up during the **dry-run week** before you leave.

---

## Architecture

```text
Dropbox folder (data owner)
        │
        ▼  rclone sync (systemd timer every 12 min)
/var/lib/bowlyzer/clubmeisterschaft/inbox/*.xlsx
        │
        ▼  clubmeisterschaft_auto_import.sh
        │    · stable-file wait (Excel double-save)
        │    · sha256 skip if unchanged
        │    · docker run → import_clubmeisterschaft_donaubowler_xlsx.py
        │    · writes ~/bowlyzer/database/data/…
        ▼
docker compose restart bowlyzer
        │
        ▼
nginx → bowlyzer.online /turnier?…Clubmeisterschaft…
```

| Artifact | Path |
|----------|------|
| Auto-import script | `scripts/clubmeisterschaft_auto_import.sh` |
| VPS installer | `scripts/install_clubmeisterschaft_auto_import.sh` |
| Env template | `deploy/vps/clubmeisterschaft-import.env.example` |
| systemd units | `deploy/vps/clubmeisterschaft-import.{service,timer}` |
| Importer | `database/input/import_clubmeisterschaft_donaubowler_xlsx.py` |

---

## Quick install (VPS)

From your **Windows** machine (after `deploy.config.ps1` exists):

```powershell
.\deploy\install_clubmeisterschaft_auto_import.ps1
```

Or on the **VPS** (git clone or scp repo there):

```bash
cd ~/bowlyzer-src   # your clone path
sudo ./scripts/install_clubmeisterschaft_auto_import.sh
sudo nano /etc/bowlyzer/clubmeisterschaft-import.env   # set CLUBMEISTERSCHAFT_RCLONE_SRC
```

---

## One-time VPS setup

### 1. Deploy a current image (before dry-run week)

On Windows:

```powershell
.\deploy\deploy.ps1 -SyncDatabase
```

The image must include `openpyxl` and the latest importer.

### 2. Install rclone and link Dropbox

```bash
sudo apt install -y rclone
rclone config   # new remote, e.g. name "dropbox", type Dropbox
```

Ask the data owner for a **dedicated subfolder** (not a public link). Example:

`dropbox:Clubmeisterschaft Donaubowler 2026/`

In `/etc/bowlyzer/clubmeisterschaft-import.env`:

```bash
CLUBMEISTERSCHAFT_RCLONE_SRC=dropbox:Clubmeisterschaft Donaubowler 2026
```

### 3. Env file

Installed by `install_clubmeisterschaft_auto_import.sh` from `deploy/vps/clubmeisterschaft-import.env.example`.

Key variables:

| Variable | Purpose |
|----------|---------|
| `BOWLYZER_DIR` | `/home/bowlyzer/bowlyzer` — compose + `database/` |
| `CLUBMEISTERSCHAFT_RCLONE_SRC` | rclone source path |
| `CLUBMEISTERSCHAFT_INBOX` | `/var/lib/bowlyzer/clubmeisterschaft/inbox` |
| `IMPORT_DATE` / `IMPORT_YEAR` | Passed to importer |

---

## Dry-run week (7 days before vacation)

Do **not** enable the systemd timer until day 6–7.

| Day | Action | Success check |
|-----|--------|----------------|
| 1 | `rclone lsd dropbox:` and `rclone ls "$CLUBMEISTERSCHAFT_RCLONE_SRC"` | Correct file visible |
| 1 | `clubmeisterschaft_auto_import.sh --sync-only` | XLSX in inbox |
| 2 | `--dry-run` after owner saves | “would import” + new hash |
| 3 | Full run (no flags) | Import logs; site matches Excel |
| 4 | Owner updates; full run; then run again | Second: `unchanged … skip` |
| 5 | Overlap two runs | Second: lock message |
| 6 | `install_clubmeisterschaft_auto_import.sh --enable-timer` | Timer fires on changes only |
| 7 | Monitor `journalctl` | Vacation-ready |

```bash
set -a && source /etc/bowlyzer/clubmeisterschaft-import.env && set +a

clubmeisterschaft_auto_import.sh --sync-only
clubmeisterschaft_auto_import.sh --dry-run
clubmeisterschaft_auto_import.sh
clubmeisterschaft_auto_import.sh   # should skip
```

Before day 6:

```bash
tar czf ~/bowlyzer-database-backup-$(date +%F).tgz -C /home/bowlyzer bowlyzer/database
```

---

## Production timer (after dry-run)

```bash
sudo ./scripts/install_clubmeisterschaft_auto_import.sh --enable-timer
journalctl -u clubmeisterschaft-import.service -f
```

---

## Failure modes

| Symptom | Fix |
|---------|-----|
| Always “unchanged” | Owner didn’t save; wrong `CLUBMEISTERSCHAFT_RCLONE_SRC` |
| “Workbook still changing” | Normal; wait for next timer tick |
| Site stale after import | `docker compose -f ~/bowlyzer/docker-compose.prod.yml restart bowlyzer` |
| `Another import is running` | Overlap — safe; increase timer interval if noisy |
| Importer error | Redeploy image: `.\deploy\deploy.ps1` |

---

## Rollback

```bash
sudo systemctl disable --now clubmeisterschaft-import.timer
# restore database/ from backup if needed
docker compose -f /home/bowlyzer/bowlyzer/docker-compose.prod.yml restart bowlyzer
```
