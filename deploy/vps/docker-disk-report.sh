#!/usr/bin/env bash
# Read-only: show what uses disk (Docker + common VPS paths). Run as root on VPS.

set -euo pipefail

echo "=== root filesystem ==="
df -h /

echo ""
echo "=== largest top-level dirs on / (may take a few seconds) ==="
du -xhd1 / 2>/dev/null | sort -h | tail -15

echo ""
echo "=== /var/lib/docker breakdown ==="
if [[ -d /var/lib/docker ]]; then
  du -xhd1 /var/lib/docker 2>/dev/null | sort -h | tail -12
fi

echo ""
echo "=== docker system df ==="
docker system df -v 2>/dev/null || docker system df 2>/dev/null || echo "(docker not running)"

echo ""
echo "=== images (size) ==="
docker images --format 'table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.ID}}' 2>/dev/null | head -30

echo ""
echo "=== containers ==="
docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Size}}' 2>/dev/null

echo ""
echo "=== container log files > 5MB ==="
find /var/lib/docker/containers -name '*-json.log' -size +5M -exec ls -lh {} \; 2>/dev/null || true

echo ""
echo "=== deploy tarballs (safe to delete after docker load) ==="
ls -lh /root/bowlyzer-image.tar /root/bowlyzer-image.tar.gz /root/bowlyzer/bowlyzer-image.tar /home/bowlyzer/bowlyzer/bowlyzer-image.tar /home/bowlyzer/bowlyzer/bowlyzer-image.tar.gz 2>/dev/null || echo "(none)"

echo ""
echo "Note: overlay mounts under /var/lib/docker/rootfs/overlayfs/ are NOT extra disk —"
echo "they share /dev/vda1 with /. Reclaim space via image prune, not by deleting overlay paths."
