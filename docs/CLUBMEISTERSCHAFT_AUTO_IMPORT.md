# Clubmeisterschaft Donaubowler — auto-import from Dropbox (VPS)

Ongoing tournament: **Clubmeisterschaft Donaubowler 2026**.  
Goal: VPS pulls the data owner’s Excel from a **dedicated Dropbox account**, imports, rebuilds **`tournaments_postprocessed.parquet`**, site updates without manual PC deploy.

**Clubpokal** (team KO) is **not** this pipeline.

---

## Who runs as what

| Action | User | Notes |
|--------|------|--------|
| Install scripts, rclone, import, timer | **`bowlyzer`** | Default; no root |
| `apt install rclone` | **root** | One-time OS package |
| `loginctl enable-linger bowlyzer` | **root** | One-time; timer runs after reboot without login |
| Docker import / merge | **`bowlyzer`** | Via `docker` group |
| App container | **`bowlyzer`** | Existing compose setup |

Legacy `/etc/bowlyzer/` and system-wide systemd units are **not** used anymore.

---

## Architecture

```text
Dedicated Dropbox user (folder shared by data owner)
        │
        ▼  step 1: rclone sync (user systemd timer, every 12 min)
~/bowlyzer/work/clubmeisterschaft/inbox/Clubpokal DB 2026.xlsx
        │
        ▼  step 2: stable-file wait + importer fingerprint (skip if unchanged)
        ▼  on change: dated .xlsx archive under work/clubmeisterschaft/archive/
        ▼  step 3: docker → import_clubmeisterschaft_donaubowler_xlsx.py
        │         → tournament_manual_postprocessed.csv
        ▼  step 4: docker → publish_tournament_parquet.py
        │         GF snapshot (host) + manual → tournaments_postprocessed.parquet
        ▼
~/bowlyzer/database/data/tournaments_postprocessed.parquet  (bind-mount :ro)
        │
        ▼  app reloads on parquet mtime (no restart by default)
bowlyzer.online /turnier?…Clubmeisterschaft…
```

| Artifact | Path |
|----------|------|
| Import script (on PATH) | `~/bin/clubmeisterschaft_auto_import.sh` |
| Config | `~/.config/bowlyzer/clubmeisterschaft-import.env` |
| rclone config | `~/.config/rclone/rclone.conf` |
| Inbox / work / state | `~/bowlyzer/work/clubmeisterschaft/` |
| GF regional snapshot | `~/bowlyzer/work/tournament_inputs/gf_tournaments_2026__combined_postprocessed.csv` |
| User systemd units | `~/.config/systemd/user/clubmeisterschaft-import.{service,timer}` |

---

## Phase A — PC (once)

```powershell
.\deploy\deploy.ps1 -SkipBuild -SyncDatabase
.\deploy\install_clubmeisterschaft_auto_import.ps1
```

Optional timer + linger in one go:

```powershell
.\deploy\install_clubmeisterschaft_auto_import.ps1 -EnableTimer -EnableLinger
```

(`-EnableLinger` SSHs as **root** once for `loginctl enable-linger bowlyzer`.)

---

## Phase B — Dropbox (dedicated account)

1. Create a **new Dropbox user** — not your personal account.
2. Data owner shares the workbook (ideally inside a **folder** — simplest for rclone).
3. Canonical workbook name: `Clubpokal DB 2026.xlsx` (dated copies excluded).

### How sharing affects rclone

| How data owner shared | Visible in `rclone ls dropbox_bowlyzer:`? | What to do |
|----------------------|------------------------------------------|------------|
| **Folder** added to your Dropbox | Yes | `CLUBMEISTERSCHAFT_RCLONE_SRC=dropbox_bowlyzer:FolderName` |
| **Folder** shared only (not in your tree) | No (use shared-folders flag) | `SHARED_FOLDERS=1` or **Add to Dropbox** in browser |
| **Single file** shared directly | `rclone ls … --dropbox-shared-files` | `SHARED_FILES=1` + `rclone cat` (not `copyto`) |

`rclone copyto` fails on shared files (`OpenOptions not supported`). The import script uses
`rclone cat` instead. **Simplest production setup:** data owner shares the file → log into the
dedicated Dropbox account in a browser → **Add to Dropbox** → then use normal folder sync.

Optional curl fallback if the link is downloadable without login:

```bash
CLUBMEISTERSCHAFT_DROPBOX_SHARED_URL=https://www.dropbox.com/scl/fi/.../Clubpokal-DB-2026.xlsx?dl=0
```

For a **directly shared file** via rclone API:

```bash
# Production: data owner shared the xlsx directly (not a folder in your tree)
# Double-quote the whole value — filename contains spaces.
CLUBMEISTERSCHAFT_RCLONE_SRC="dropbox_bowlyzer:Clubpokal DB 2026.xlsx"
CLUBMEISTERSCHAFT_RCLONE_SHARED_FILES=1
CLUBMEISTERSCHAFT_XLSX_NAME="Clubpokal DB 2026.xlsx"
```

`rclone ls … --dropbox-shared-files` may show size `0` — that is normal for the listing API;
verify with `rclone cat … --dropbox-shared-files > /tmp/test.xlsx` and check file size (~20 KB).

```bash
CLUBMEISTERSCHAFT_RCLONE_SRC=dropbox_bowlyzer:Clubmeisterschaft_Donaubowler
CLUBMEISTERSCHAFT_RCLONE_SHARED_FILES=0
```

Test: `clubmeisterschaft_auto_import.sh --sync-only`

---

## Phase C — VPS setup (as bowlyzer)

```bash
# one-time OS package (root)
sudo apt install -y rclone

# as bowlyzer
cd ~/bowlyzer-src
./scripts/install_clubmeisterschaft_auto_import.sh

rclone config   # remote name: dropbox

nano ~/.config/bowlyzer/clubmeisterschaft-import.env
# CLUBMEISTERSCHAFT_RCLONE_SRC=dropbox:YourFolder

./scripts/bootstrap_clubmeisterschaft_dropbox.sh
```

---

## Phase D — Dry-run

```bash
set -a && source ~/.config/bowlyzer/clubmeisterschaft-import.env && set +a

clubmeisterschaft_auto_import.sh --sync-only
clubmeisterschaft_auto_import.sh --dry-run
clubmeisterschaft_auto_import.sh
clubmeisterschaft_auto_import.sh   # unchanged … skip
```

---

## Phase E — Enable timer

```bash
./scripts/install_clubmeisterschaft_auto_import.sh --enable-timer

# once as root (timers after reboot without login):
sudo ./scripts/install_clubmeisterschaft_linger.sh
```

```bash
journalctl --user -u clubmeisterschaft-import.service -f
```

If you previously installed system-wide units:

```bash
sudo systemctl disable --now clubmeisterschaft-import.timer 2>/dev/null || true
```

### Timer troubleshooting

Healthy timer:

```bash
systemctl --user list-timers clubmeisterschaft-import.timer
# NEXT and LEFT must show a future time — not "-"
```

| Symptom | Cause / fix |
|---------|-------------|
| `NEXT: -`, `Active: active (elapsed)`, no new journal entries | Timer not scheduling — use `OnUnitInactiveSec` (not `OnUnitActiveSec`) for oneshot services; `daemon-reload` + `restart` timer |
| `disabled` / `inactive (dead)` | Run `install_clubmeisterschaft_auto_import.sh --enable-timer` |
| `Linger=no` | `sudo loginctl enable-linger bowlyzer` |
| Inbox stale but Dropbox has new file | Timer not running, or hash skip — run manual import |
| Import + email every 2 min, same row counts | Fingerprint must use importer `--fingerprint` (parsed sheet rows), not raw file sha256 |

**Env file and spaces:** Values with spaces must be **double-quoted as a whole** (works for both systemd and `source`).

| Format | Result |
|--------|--------|
| `VAR=dropbox_bowlyzer:Clubpokal DB 2026.xlsx` | **Broken** — bash runs `DB` as a command; systemd truncates at the first space |
| `VAR=dropbox_bowlyzer:"Clubpokal DB 2026.xlsx"` | **Broken** — partial quotes; literal `"` passed to rclone |
| `VAR="dropbox_bowlyzer:Clubpokal DB 2026.xlsx"` | **Correct** — outer quotes stripped by systemd and bash |

```bash
CLUBMEISTERSCHAFT_RCLONE_SRC="dropbox_bowlyzer:Clubpokal DB 2026.xlsx"
CLUBMEISTERSCHAFT_RCLONE_SHARED_FILES=1
CLUBMEISTERSCHAFT_XLSX_NAME="Clubpokal DB 2026.xlsx"
```

Verify after editing:

```bash
set -a && source ~/.config/bowlyzer/clubmeisterschaft-import.env && set +a
printf '%s\n' "$CLUBMEISTERSCHAFT_RCLONE_SRC" "$CLUBMEISTERSCHAFT_XLSX_NAME"
# expect: dropbox_bowlyzer:Clubpokal DB 2026.xlsx  (no quotes)
```

After fixing timer unit on VPS:

```bash
cp ~/bowlyzer/deploy/vps/user/clubmeisterschaft-import.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user restart clubmeisterschaft-import.timer

# start without blocking the shell (oneshot import can take 1–5+ min)
systemctl --user start --no-block clubmeisterschaft-import.service
journalctl --user -u clubmeisterschaft-import.service -f
```

`systemctl start` (without `--no-block`) **waits until the import finishes** — at least the 30s stable-file sleep, plus Docker when the workbook hash changed. That is normal, not a hang. Ctrl+C only stops `systemctl`, not the import job.

---

## Root-only summary

| Command | Why root |
|---------|----------|
| `apt install rclone` | system packages |
| `install_clubmeisterschaft_linger.sh` | `loginctl enable-linger` |

Everything else: **bowlyzer**.

---

## Rollback

```bash
systemctl --user disable --now clubmeisterschaft-import.timer
```

Restore `~/bowlyzer/database/` from backup if needed.

---

## Workbook archive on import

When the import **fingerprint** changes, a copy of the workbook is saved before import:

`~/bowlyzer/work/clubmeisterschaft/archive/Clubpokal DB 2026_YYYY_MM_DD.xlsx`

If that name already exists the same day, suffixes increment: `_2`, `_3`, …

Override directory with `CLUBMEISTERSCHAFT_ARCHIVE` in `clubmeisterschaft-import.env`.

---

## Email on new workbook

When the workbook **import fingerprint** changes and import + parquet publish succeed, the script emails
`CLUBMEISTERSCHAFT_NOTIFY_EMAIL` the **full run log** (rclone, import, publish, warnings).

Set SMTP in `~/.config/bowlyzer/clubmeisterschaft-import.env` (file mode **600**).
If `NOTIFY_SMTP_HOST` is unset, import still runs; a log line notes that email was skipped.

### IONOS (VPS + `bowlyzer.online` mail) — recommended

Your setup is a good match: the VPS does **not** send mail directly. It logs in to **IONOS Mail**
(`smtp.ionos.com`) like Thunderbird would — outbound port **587**, authenticated relay.
IONOS VPS often blocks raw **port 25**; that does not matter here.

**1. Mailbox in IONOS**

In the IONOS control panel → **Email** → use an existing address (e.g. `chris@bowlyzer.online`)
or create one (e.g. `notifications@bowlyzer.online`).

**2. Password**

- **No 2FA on webmail:** use the normal mailbox password.
- **2FA enabled:** regular password will **not** work for SMTP. In [IONOS Webmail](https://mail.ionos.com)
  → top-right account menu → **Login & Security** → create an **app password** and use that as
  `NOTIFY_SMTP_PASS`.

**3. Env on VPS** (`~/.config/bowlyzer/clubmeisterschaft-import.env`)

```bash
CLUBMEISTERSCHAFT_NOTIFY_EMAIL=chris@bowlyzer.online
NOTIFY_EMAIL_FROM=chris@bowlyzer.online
NOTIFY_SMTP_HOST=smtp.ionos.com
NOTIFY_SMTP_PORT=587
NOTIFY_SMTP_USER=chris@bowlyzer.online
NOTIFY_SMTP_PASS=your-mailbox-or-app-password
NOTIFY_SMTP_STARTTLS=1
```

| Variable | IONOS value | Notes |
|----------|-------------|--------|
| `NOTIFY_SMTP_HOST` | `smtp.ionos.com` | Same for `.de` / `.com` domains |
| `NOTIFY_SMTP_PORT` | `587` or `465` | 587 + `NOTIFY_SMTP_STARTTLS=1`, or 465 + `NOTIFY_SMTP_SSL=1` |
| `NOTIFY_SMTP_USER` | Full email address | Not just `chris` — must be `chris@bowlyzer.online` |
| `NOTIFY_EMAIL_FROM` | Same mailbox (or alias on same domain) | IONOS may reject if From domain ≠ auth user |
| `NOTIFY_SMTP_PASS` | Mailbox or app password | Prefer separate file (below) |

**Port 465:** If 587 returns `535`, try IONOS’s SSL port instead:

```bash
NOTIFY_SMTP_PORT=465
NOTIFY_SMTP_SSL=1
NOTIFY_SMTP_STARTTLS=0
```

**4. Keep password out of the main env file (optional)**

```bash
printf '%s\n' 'your-app-password' > ~/.config/bowlyzer/notify-smtp.pass
chmod 600 ~/.config/bowlyzer/notify-smtp.pass
```

In `clubmeisterschaft-import.env`:

```bash
NOTIFY_SMTP_PASS_FILE=/home/bowlyzer/.config/bowlyzer/notify-smtp.pass
# omit NOTIFY_SMTP_PASS
```

**5. Load env and test**

```bash
chmod 600 ~/.config/bowlyzer/clubmeisterschaft-import.env
set -a && source ~/.config/bowlyzer/clubmeisterschaft-import.env && set +a

printf 'Bowlyzer SMTP test\n' > /tmp/notify-test.txt
python3 ~/bowlyzer/scripts/send_notify_email.py \
  --to chris@bowlyzer.online \
  --subject "Bowlyzer notify test" \
  --body-file /tmp/notify-test.txt
```

**Typical errors**

| Message | Fix |
|---------|-----|
| `535 Authentication credentials invalid` | Wrong password; or 2FA on → use app password; user must be full email |
| `Sender address rejected` | Set `NOTIFY_EMAIL_FROM` to the same address as `NOTIFY_SMTP_USER` |
| Connection timeout on 587 | Rare on IONOS VPS; check `ufw`/firewall allows **outbound** 587 |
| `535` on 587 but Thunderbird works | Try port **465** with `NOTIFY_SMTP_SSL=1` and `NOTIFY_SMTP_STARTTLS=0` |
| `NOTIFY_SMTP_HOST unset` | Env not loaded in systemd — vars must be in `clubmeisterschaft-import.env` (service uses `EnvironmentFile`) |

### Other providers (Resend, SendGrid, …)

Same env shape; use the provider’s SMTP host, port 587, and API key or SMTP credentials.
Useful if you do not host mail on IONOS.
