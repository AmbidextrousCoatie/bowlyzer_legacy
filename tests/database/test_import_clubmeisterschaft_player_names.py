"""Clubmeisterschaft player display names → Family, Given."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
IMPORTER_PATH = REPO_ROOT / "scripts" / "data" / "import_clubmeisterschaft_donaubowler_xlsx.py"


def _load_importer():
    spec = importlib.util.spec_from_file_location("import_clubmeisterschaft_donaubowler_xlsx", IMPORTER_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def club():
    return _load_importer()


def test_canonicalize_player_display_name_to_family_given(club) -> None:
    assert club._canonicalize_player_display_name("Christian Feller") == "Feller, Christian"
    assert club._canonicalize_player_display_name("Feller, Christian") == "Feller, Christian"
    assert club._canonicalize_player_display_name("Volkmar Harteil") == "Hartfeil, Volkmar"
    assert club._canonicalize_player_display_name("Luu Vinh Duc") == "Luu, Vinh Duc"


def test_canonicalize_does_not_invert_to_given_family(club) -> None:
    """Regression: finale path used to flip Last, First → First Last."""
    assert club._canonicalize_player_display_name("Hartfeil, Volkmar") == "Hartfeil, Volkmar"
    assert "," in club._canonicalize_player_display_name("Tobias Schneider")
