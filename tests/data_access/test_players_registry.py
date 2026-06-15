"""Players registry build + apply."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from data_access.players_registry import (
    apply_players_registry,
    build_registry_dataframe,
    canonical_name_for_player_id,
    merge_registry_dataframes,
    registry_accepts_all_names_for_id,
    registry_lookup_by_id,
    registry_name_index,
    resolve_player_id_for_name,
    resolve_player_name_for_id,
    write_players_registry,
)
from data_access.schema import Columns


def _write_id_name_config(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "version": 2,
                "manual_resolutions": {
                    "dbu_id": [
                        {
                            "match": {"player_name": "Alt, Name", "player_id": "100"},
                            "replace": {"player_id": "200"},
                            "source": "dbu_id",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )


def _write_name_config(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "manual_resolutions": {
                    "dbu_id": [
                        {
                            "match": {"player_name": "Vogt Thomas", "player_id": "10903"},
                            "replace": {"player_name": "Vogt, Thomas"},
                            "source": "dbu_id",
                        }
                    ],
                    "same_person": [
                        {
                            "player_id": "16116",
                            "player_names": [
                                "Förster, Heike",
                                "Müller, Heike",
                                "Schmidt, Heike",
                            ],
                        },
                        {
                            "player_id": "16032",
                            "player_names": ["O'Steen, Daniel", "O`Steen, Daniel"],
                        },
                    ],
                },
            }
        ),
        encoding="utf-8",
    )


def test_build_registry_from_configs(tmp_path: Path, monkeypatch) -> None:
    id_cfg = tmp_path / "player_id_name_normalization.json"
    name_cfg = tmp_path / "player_name_normalization.json"
    _write_id_name_config(id_cfg)
    _write_name_config(name_cfg)
    monkeypatch.setattr(
        "data_access.players_registry.load_player_id_name_normalization_config",
        lambda path=None: __import__(
            "data_access.player_id_name_normalization",
            fromlist=["load_player_id_name_normalization_config"],
        ).load_player_id_name_normalization_config(id_cfg),
    )
    monkeypatch.setattr(
        "data_access.players_registry.load_player_name_normalization_config",
        lambda path=None: __import__(
            "data_access.player_name_normalization_config",
            fromlist=["load_player_name_normalization_config"],
        ).load_player_name_normalization_config(name_cfg),
    )

    df = build_registry_dataframe()
    assert len(df) >= 4
    row = df.loc[df["player_id"] == "200"].iloc[0]
    assert row["canonical_name"] == "Alt, Name"
    marriage = df.loc[df["player_id"] == "16116"].iloc[0]
    assert marriage["canonical_name"] == "Förster, Heike"
    assert "Müller, Heike" in marriage["aliases"]
    assert "Schmidt, Heike" in marriage["aliases"]


def test_resolve_particle_and_generation_identity() -> None:
    lookup = registry_lookup_by_id(
        pd.DataFrame(
            [
                {
                    "player_id": "7439",
                    "canonical_name": "Weverberg, Susanne van",
                    "source": "dbu_id",
                    "updated_at": "t",
                    "aliases": "Van Weverberg, Susanne",
                },
                {
                    "player_id": "7408",
                    "canonical_name": "Glasl jun., Hans-Jürgen",
                    "source": "dbu_id",
                    "updated_at": "t",
                    "aliases": "Glasl, Hans-Jürgen|Hans-Jürgen Glasl",
                },
            ]
        )
    )
    resolved, kind = resolve_player_name_for_id("Weverberg Van, Susanne", "7439", lookup)
    assert kind in {"identity", "reassembly"}
    assert resolved == "Weverberg, Susanne van"

    resolved_glasl, kind_glasl = resolve_player_name_for_id(
        "Hans-Jürgen Glasl sen.", "7408", lookup
    )
    assert kind_glasl in {"identity", "reassembly"}
    assert resolved_glasl in {"Glasl jun., Hans-Jürgen", "Glasl, Hans-Jürgen", "Hans-Jürgen Glasl"}


def test_resolve_abbreviated_given_name() -> None:
    lookup = registry_lookup_by_id(
        pd.DataFrame(
            [
                {
                    "player_id": "7253",
                    "canonical_name": "Kortenacker, Hans-Jürgen",
                    "source": "dbu_id",
                    "updated_at": "t",
                    "aliases": "Kortenacker, Hans Jürgen",
                }
            ]
        )
    )
    resolved, kind = resolve_player_name_for_id("Kortenacker, Hans", "7253", lookup)
    assert kind == "abbrev"
    assert resolved == "Kortenacker, Hans-Jürgen"


def test_resolve_two_token_reversal_against_single_candidate() -> None:
    lookup = registry_lookup_by_id(
        pd.DataFrame(
            [
                {
                    "player_id": "25604",
                    "canonical_name": "Seltmann, Dominic",
                    "source": "dbu_id",
                    "updated_at": "t",
                    "aliases": "Seltmann, Dominik",
                }
            ]
        )
    )
    resolved, kind = resolve_player_name_for_id("Dominik Seltmann", "25604", lookup)
    assert kind == "reassembly"
    assert resolved == "Seltmann, Dominik"

    typo, kind_typo = resolve_player_name_for_id("Sltmann, Dominik", "25604", lookup)
    assert kind_typo == "close"
    assert typo == "Seltmann, Dominik"

    nickname, kind_nick = resolve_player_name_for_id("Seltmann, Dominic", "25604", lookup)
    assert kind_nick == "exact"
    assert nickname == "Seltmann, Dominic"


def test_resolve_substring_given_name() -> None:
    lookup = registry_lookup_by_id(
        pd.DataFrame(
            [
                {
                    "player_id": "7596",
                    "canonical_name": "Groll, Alexander",
                    "source": "dbu_id",
                    "updated_at": "t",
                    "aliases": "Groll, Alex",
                },
                {
                    "player_id": "25354",
                    "canonical_name": "Huber, Carina-Maren",
                    "source": "dbu_id",
                    "updated_at": "t",
                    "aliases": "Huber, Carina|Huber, Carina Mareen",
                },
            ]
        )
    )
    alex, kind_alex = resolve_player_name_for_id("Groll, Alex", "7596", lookup)
    assert kind_alex in {"exact", "abbrev", "substring"}
    assert alex in {"Groll, Alex", "Groll, Alexander"}

    longer, kind_longer = resolve_player_name_for_id("Groll, Alexander", "7596", lookup)
    assert kind_longer == "exact"
    assert longer == "Groll, Alexander"

    lookup_nick_only = registry_lookup_by_id(
        pd.DataFrame(
            [
                {
                    "player_id": "7596",
                    "canonical_name": "Groll, Alexander",
                    "source": "dbu_id",
                    "updated_at": "t",
                    "aliases": "",
                }
            ]
        )
    )
    nick, kind_nick = resolve_player_name_for_id("Groll, Alex", "7596", lookup_nick_only)
    assert kind_nick in {"abbrev", "substring"}
    assert nick == "Groll, Alexander"

    carina, kind_carina = resolve_player_name_for_id("Huber, Carina Mareen", "25354", lookup)
    assert kind_carina in {"exact", "abbrev", "substring"}
    assert carina in {"Huber, Carina Mareen", "Huber, Carina-Maren"}

    short_carina, kind_short = resolve_player_name_for_id("Huber, Carina", "25354", lookup)
    assert kind_short in {"exact", "abbrev", "substring"}
    assert short_carina in {"Huber, Carina", "Huber, Carina-Maren"}

    assert registry_accepts_all_names_for_id(
        "7596",
        {"Groll, Alex", "Groll, Alexander"},
        lookup,
    )
    assert registry_accepts_all_names_for_id(
        "25354",
        {"Huber, Carina", "Huber, Carina Mareen", "Huber, Carina-Maren"},
        lookup,
    )


def test_resolve_maximilian_substring_and_dual_typo() -> None:
    lookup = registry_lookup_by_id(
        pd.DataFrame(
            [
                {
                    "player_id": "25822",
                    "canonical_name": "Kammermeier, Maximilian",
                    "source": "dbu_id",
                    "updated_at": "t",
                    "aliases": "Maximilian Kammermeier",
                },
                {
                    "player_id": "38309",
                    "canonical_name": "Pafford, Mark",
                    "source": "dbu_id",
                    "updated_at": "t",
                    "aliases": "Pfafford, Mark",
                },
            ]
        )
    )
    max_name, max_kind = resolve_player_name_for_id("Kammermeier, Max", "25822", lookup)
    assert max_kind in {"abbrev", "substring"}
    assert max_name == "Kammermeier, Maximilian"

    marc, marc_kind = resolve_player_name_for_id("Paffort, Marc", "38309", lookup)
    assert marc_kind == "close"
    assert marc == "Pafford, Mark"


def test_resolve_player_id_for_name() -> None:
    registry = pd.DataFrame(
        [
            {
                "player_id": "25977",
                "canonical_name": "Erhard, Hannelore",
                "source": "dbu_id",
                "updated_at": "t",
                "aliases": "",
            },
            {
                "player_id": "38424",
                "canonical_name": "Gulvadi, Sanat",
                "source": "dbu_id",
                "updated_at": "t",
                "aliases": "",
            },
        ]
    )
    lookup = registry_lookup_by_id(registry)
    index = registry_name_index(registry)
    pid, kind = resolve_player_id_for_name("Erhard, Hannelore", index, lookup)
    assert kind == "exact"
    assert pid == "25977"
    gulvadi_pid, g_kind = resolve_player_id_for_name("Gulvadi, Sanat", index, lookup)
    assert g_kind == "exact"
    assert gulvadi_pid == "38424"


def test_resolve_typo_close_match() -> None:
    lookup = registry_lookup_by_id(
        pd.DataFrame(
            [
                {
                    "player_id": "200",
                    "canonical_name": "Müller, Heike",
                    "source": "same_person_alias",
                    "updated_at": "t",
                    "aliases": "Förster, Heike|Schmidt, Heike",
                }
            ]
        )
    )
    resolved, kind = resolve_player_name_for_id("Mueller, Heike", "200", lookup)
    assert kind == "close"
    assert resolved == "Müller, Heike"

    exact, kind_exact = resolve_player_name_for_id("Förster, Heike", "200", lookup)
    assert kind_exact == "exact"
    assert exact == "Förster, Heike"


def test_resolve_unknown_name_unresolved() -> None:
    lookup = registry_lookup_by_id(
        pd.DataFrame(
            [
                {
                    "player_id": "200",
                    "canonical_name": "Müller, Heike",
                    "source": "same_person_alias",
                    "updated_at": "t",
                    "aliases": "Förster, Heike",
                }
            ]
        )
    )
    resolved, kind = resolve_player_name_for_id("Wagner, Heike", "200", lookup)
    assert resolved is None
    assert kind == "unresolved"


def test_registry_accepts_subset_of_marriage_names() -> None:
    lookup = registry_lookup_by_id(
        pd.DataFrame(
            [
                {
                    "player_id": "16116",
                    "canonical_name": "Förster, Heike",
                    "source": "same_person_alias",
                    "updated_at": "t",
                    "aliases": "Müller, Heike|Schmidt, Heike",
                }
            ]
        )
    )
    assert registry_accepts_all_names_for_id("16116", {"Müller, Heike", "Förster, Heike"}, lookup)
    assert not registry_accepts_all_names_for_id("16116", {"Müller, Heike", "Wagner, Heike"}, lookup)


def test_apply_players_registry_normalizes_format_alias_to_canonical() -> None:
    registry = pd.DataFrame(
        [
            {
                "player_id": "12248",
                "canonical_name": "Burghardt, Mario",
                "source": "dbu_id",
                "updated_at": "2026-06-09T00:00:00+00:00",
                "aliases": "Mario Burghardt",
            }
        ]
    )
    frame = pd.DataFrame(
        {
            Columns.player_id: ["12248", "12248"],
            Columns.player_name: ["Mario Burghardt", "Burghardt, Mario"],
        }
    )
    out, stats = apply_players_registry(frame, registry)
    assert out[Columns.player_name].tolist() == ["Burghardt, Mario", "Burghardt, Mario"]
    assert stats["registry_alias_to_canonical"] == 1
    assert stats["registry_unchanged"] == 1


def test_apply_players_registry_keeps_marriage_alias() -> None:
    registry = pd.DataFrame(
        [
            {
                "player_id": "16116",
                "canonical_name": "Förster, Heike",
                "source": "same_person_alias",
                "updated_at": "2026-06-09T00:00:00+00:00",
                "aliases": "Müller, Heike",
            }
        ]
    )
    frame = pd.DataFrame(
        {
            Columns.player_id: ["16116", "16116"],
            Columns.player_name: ["Müller, Heike", "Förster, Heike"],
        }
    )
    out, stats = apply_players_registry(frame, registry)
    assert out[Columns.player_name].tolist() == ["Müller, Heike", "Förster, Heike"]
    assert stats["registry_alias_to_canonical"] == 0
    assert stats["registry_unchanged"] == 2


def test_apply_players_registry_typo_not_forced_canonical() -> None:
    registry = pd.DataFrame(
        [
            {
                "player_id": "16116",
                "canonical_name": "Förster, Heike",
                "source": "same_person_alias",
                "updated_at": "2026-06-09T00:00:00+00:00",
                "aliases": "Müller, Heike",
            }
        ]
    )
    frame = pd.DataFrame(
        {
            Columns.player_id: ["16116", "16116"],
            Columns.player_name: ["Müller, Heike", "Mueller, Heike"],
        }
    )
    out, stats = apply_players_registry(frame, registry)
    assert out.loc[0, Columns.player_name] == "Müller, Heike"
    assert out.loc[1, Columns.player_name] == "Müller, Heike"
    assert stats["registry_close"] == 1
    assert stats["registry_unchanged"] == 1


def test_merge_preserves_published_canonical_over_majority() -> None:
    base = pd.DataFrame(
        [
            {
                "player_id": "7001",
                "canonical_name": "Official, Name",
                "source": "dbu_id",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "aliases": "",
            }
        ]
    )
    updates = pd.DataFrame(
        [
            {
                "player_id": "7001",
                "canonical_name": "Offical, Name",
                "source": "majority",
                "updated_at": "2026-06-09T00:00:00+00:00",
                "aliases": "Offical, Name",
            }
        ]
    )
    merged = merge_registry_dataframes(base, updates)
    row = merged.loc[merged["player_id"] == "7001"].iloc[0]
    assert row["canonical_name"] == "Official, Name"
    assert "Offical, Name" in row["aliases"]


def test_same_person_preserves_json_order_primary(tmp_path: Path, monkeypatch) -> None:
    name_cfg = tmp_path / "player_name_normalization.json"
    name_cfg.write_text(
        json.dumps(
            {
                "version": 1,
                "manual_resolutions": {
                    "same_person": [
                        {
                            "player_id": "16116",
                            "player_names": [
                                "Förster, Heike",
                                "Müller, Heike",
                            ],
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "data_access.players_registry.load_player_id_name_normalization_config",
        lambda path=None: __import__(
            "data_access.player_id_name_normalization",
            fromlist=["load_player_id_name_normalization_config"],
        ).load_player_id_name_normalization_config(tmp_path / "missing.json"),
    )
    monkeypatch.setattr(
        "data_access.players_registry.load_player_name_normalization_config",
        lambda path=None: __import__(
            "data_access.player_name_normalization_config",
            fromlist=["load_player_name_normalization_config"],
        ).load_player_name_normalization_config(name_cfg),
    )
    df = build_registry_dataframe()
    row = df.loc[df["player_id"] == "16116"].iloc[0]
    assert row["canonical_name"] == "Förster, Heike"
    assert "Müller, Heike" in row["aliases"]


def test_write_and_load_registry(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("BOWLYZER_DATA_DIR", str(data_dir))

    registry = pd.DataFrame(
        [
            {
                "player_id": "42",
                "canonical_name": "Test, Player",
                "source": "manual",
                "updated_at": "2026-06-09T00:00:00+00:00",
                "aliases": "",
            }
        ]
    )
    write_players_registry(registry)
    assert canonical_name_for_player_id("42") == "Test, Player"
