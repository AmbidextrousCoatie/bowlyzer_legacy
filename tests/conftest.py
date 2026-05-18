"""
Pytest configuration shared by all tests.

Adds the repository root to sys.path so imports like `app` and `data_access` work.
Domain / application / infrastructure tests live under tests/ but are excluded via
pyproject.toml — that code targets a v2 package tree not shipped in this repo.
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
