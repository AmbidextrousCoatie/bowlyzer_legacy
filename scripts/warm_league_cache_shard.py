#!/usr/bin/env python3
"""
Deprecated wrapper — use ``warm_cache_shard.py`` instead.

Forwards all CLI arguments to ``scripts/warm_cache_shard.py``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "scripts" / "warm_cache_shard.py"


def main() -> int:
    print(
        "Note: warm_league_cache_shard.py was renamed to warm_cache_shard.py "
        "(league + player + tournament). Forwarding …",
        file=sys.stderr,
        flush=True,
    )
    cmd = [sys.executable, str(TARGET), *sys.argv[1:]]
    # Prefer uv run when launched via uv
    if "uv" in Path(sys.executable).name.lower() or True:
        cmd = ["uv", "run", "python", str(TARGET), *sys.argv[1:]]
    proc = subprocess.run(cmd, cwd=ROOT)
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
