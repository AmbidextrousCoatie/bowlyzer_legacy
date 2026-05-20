# VPS disk space and non-root deploy (`bowlyzer` user)

Small VPS (~9 GB) fills quickly because each `deploy.ps1` run uploads a saved image (`bowlyzer-image.tar.gz` after gzip) under `~/bowlyzer/` until `docker load` removes it — and because Docker layers accumulate.

**Note:** `docker save` produces an **uncompressed** tar; the script **gzip**s it before `scp` so uploads match the smaller on-wire size (~100–250 MB typical), not the full ~1 GB layer size.

---

## Immediate relief (run on VPS as root now)

```bash
# Free ~80–250 MB: leftover deploy tarball in /root
rm -f /root/bowlyzer-image.tar /root/bowlyzer-image.tar.gz

# Optional: repo script (also prunes Docker + apt cache)
curl -sSL https://raw.githubusercontent.com/YOUR_ORG/bowlyzer_deploy/main/deploy/vps/cleanup-disk.sh -o /tmp/cleanup-disk.sh
# or copy from repo after scp:
sudo bash deploy/vps/cleanup-disk.sh
```

See what uses space:

```bash
sudo bash deploy/vps/docker-disk-report.sh
```

Manual Docker cleanup (safe → stronger):

```bash
docker system df
docker system prune -f
docker image prune -a -f    # removes ALL images not used by a running container
docker builder prune -a -f  # if you ever built on the VPS
```

Or one script:

```bash
sudo bash deploy/vps/cleanup-disk.sh
sudo bash deploy/vps/cleanup-disk.sh --aggressive   # if still >90%
```

Check space:

```bash
df -h /
du -sh /root/* /var/lib/docker 2>/dev/null | sort -h
```

---

## Docker overlay lines are not “extra” disk

Lines like:

```text
overlay  8.7G  8.2G  481M  95%  /var/lib/docker/rootfs/overlayfs/bf83589f…
```

are **the same** space as `/` on `/dev/vda1`. Overlay is how the running container sees its filesystem; deleting anything under `overlayfs/` by hand will break Docker.

Reclaim space with **image prune**, not by editing overlay paths.

## Why disk was 94% full

| Item | Typical size | Notes |
|------|----------------|-------|
| `/var/lib/docker` | often **3–5+ GB** on 9 GB VPS | Stacked image layers; **each deploy** can leave an old `bowlyzer:release` layer |
| `/root/bowlyzer-image.tar.gz` (or `.tar`) | leftover from deploy | **Safe to delete** after `docker load` |
| Dangling / old images | 1–3 GB | `docker image prune -a` |
| Container JSON logs | 100MB–1GB+ | Truncated by `cleanup-disk.sh` |
| `~/bowlyzer/database/` | varies | Keep — live data |

**From the next deploy onward**, `deploy.ps1` **removes the uploaded `.tar.gz` after `docker load`** and runs `docker image prune -f`.

---

## Non-root deploy user

| Layer | User |
|-------|------|
| SSH / `docker compose` on VPS | Linux user **`bowlyzer`** (in group `docker`) |
| Process inside container | UID **1000** (`bowlyzer`) — not root |
| Legacy `flaskuser` / `flaskapp` | Unchanged; keep **disabled** if you use Docker |

### One-time migration (as root)

If the script was copied from Windows and bash reports `$'\r': command not found`:

```bash
sed -i 's/\r$//' /tmp/setup-bowlyzer-user.sh
```

```bash
# On VPS — copy repo or scp deploy/vps/*.sh
sudo bash deploy/vps/setup-bowlyzer-user.sh --migrate-from-root
sudo bash deploy/vps/cleanup-disk.sh

# SSH key for bowlyzer (from your PC)
ssh-copy-id bowlyzer@212.227.57.223
```

On Windows, update `deploy/deploy.config.ps1`:

```powershell
RemoteUser = "bowlyzer"
RemoteDir  = "/home/bowlyzer/bowlyzer"
```

Then deploy:

```powershell
.\deploy\deploy.ps1 -SyncDatabase
```

### Permissions

- `~/bowlyzer/database/` owned by **bowlyzer:bowlyzer** (import job writes CSVs here).
- `~/bowlyzer/.env` mode **600**, owner bowlyzer.
- nginx still runs as `www-data` and proxies to `127.0.0.1:8080` — no change.

---

## What we do *not* recommend

- Leaving `bowlyzer-image.tar` / `bowlyzer-image.tar.gz` in `/root/` or `~/bowlyzer/` after deploy.
- Running the app container as root (removed in Dockerfile + compose `user: "1000:1000"`).
- Using Dropbox shared links for auto-import (see `CLUBMEISTERSCHAFT_AUTO_IMPORT.md`).

---

## Related files

| File | Purpose |
|------|---------|
| `deploy/vps/cleanup-disk.sh` | Disk recovery |
| `deploy/vps/setup-bowlyzer-user.sh` | Create `bowlyzer` user + migrate from `/root/bowlyzer` |
| `deploy/deploy.ps1` | Gzip deploy artifact; remote `rm` after `docker load` |
| `Dockerfile` | `USER bowlyzer` (UID 1000) |
