#!/usr/bin/env python3
"""Interactive CSV / Parquet inspector for Bowl-A-Lyzer data artifacts."""

from __future__ import annotations

import json
import re
import shlex
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "database/config/cav_inspector_files.json"
SUPPORTED_SUFFIXES = {".csv", ".parquet"}


def repo_relative(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def load_config() -> dict:
    if not CONFIG_PATH.is_file():
        return {"schema_version": 1, "files": []}
    with CONFIG_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def save_config(config: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_PATH.open("w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def add_file_to_config(label: str, path: Path) -> None:
    config = load_config()
    rel_path = repo_relative(path)
    files = config.setdefault("files", [])
    for entry in files:
        if entry.get("path") == rel_path:
            entry["label"] = label
            save_config(config)
            return
    files.append({"label": label, "path": rel_path})
    save_config(config)


def _read_csv_auto(path: Path) -> pd.DataFrame:
    best: pd.DataFrame | None = None
    for sep in (";", ","):
        try:
            candidate = pd.read_csv(path, sep=sep, low_memory=False)
        except pd.errors.ParserError:
            continue
        if best is None or len(candidate.columns) > len(best.columns):
            best = candidate
    if best is not None and len(best.columns) > 1:
        return best
    return pd.read_csv(path, low_memory=False)


def load_dataframe(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".csv":
        return _read_csv_auto(path)
    raise ValueError(f"Unsupported file type: {suffix}")


def season_sort_key(value: object) -> tuple[int, str]:
    text = str(value).strip()
    match = re.match(r"(\d{4})", text)
    if match:
        return (int(match.group(1)), text)
    return (10**9, text)


def resolve_column_tokens(columns: list[str], tokens: list[str]) -> list[str]:
    selected: list[str] = []
    for token in tokens:
        stripped = token.strip()
        if not stripped:
            continue
        if stripped.isdigit():
            index = int(stripped) - 1
            if index < 0 or index >= len(columns):
                raise ValueError(f"Column id out of range: {stripped}")
            selected.append(columns[index])
            continue
        if stripped in columns:
            selected.append(stripped)
            continue
        matches = [col for col in columns if col.casefold() == stripped.casefold()]
        if len(matches) == 1:
            selected.append(matches[0])
            continue
        if matches:
            raise ValueError(f"Ambiguous column name: {stripped}")
        raise ValueError(f"Unknown column: {stripped}")
    if not selected:
        raise ValueError("No columns selected")
    return selected


def resolve_column_token(columns: list[str], token: str) -> str:
    return resolve_column_tokens(columns, [token])[0]


def parse_filter_args(arg: str) -> tuple[str, str]:
    parts = shlex.split(arg, posix=False)
    if len(parts) < 2:
        raise ValueError('Usage: f <col_id_or_name> <substring>  (e.g. f 2 "Feller")')
    column_token = parts[0]
    needle = parts[1]
    if len(needle) >= 2 and needle[0] == needle[-1] and needle[0] in "'\"":
        needle = needle[1:-1]
    return column_token, needle


def filter_substring(df: pd.DataFrame, column: str, needle: str) -> pd.DataFrame:
    series = df[column].astype(str)
    mask = series.str.contains(needle, case=False, na=False, regex=False)
    return df.loc[mask]


def format_column_menu(columns: list[str]) -> str:
    lines = ["Columns:"]
    for index, column in enumerate(columns, start=1):
        lines.append(f"  {index:>3}  {column}")
    return "\n".join(lines)


def slice_summary(df: pd.DataFrame, *, source_label: str | None = None) -> str:
    lines: list[str] = []
    if source_label:
        lines.append(f"Source: {source_label}")
    lines.append(f"Dimensions: {len(df):,} rows x {len(df.columns)} cols")

    if "Season" in df.columns:
        seasons = [value for value in df["Season"].dropna().astype(str).str.strip() if value]
        if seasons:
            ordered = sorted(seasons, key=season_sort_key)
            lines.append(f"Seasons: {ordered[0]} .. {ordered[-1]} ({len(set(seasons))} unique)")

    if "Event Type" in df.columns:
        counts = df["Event Type"].astype(str).str.strip().str.casefold().value_counts()
        league_rows = int(counts.get("league", 0))
        tournament_rows = int(counts.get("tournament", 0))
        parts: list[str] = []
        if league_rows:
            parts.append(f"league={league_rows:,}")
        if tournament_rows:
            parts.append(f"tournament={tournament_rows:,}")
        if parts:
            lines.append(f"Event types: {', '.join(parts)}")
        other = len(df) - league_rows - tournament_rows
        if other:
            lines.append(f"Other event rows: {other:,}")
    elif "Event" in df.columns:
        events = df["Event"].dropna().astype(str).str.strip()
        unique_events = events[events != ""].nunique()
        if unique_events:
            lines.append(f"Events: {unique_events:,} unique")

    lines.append(f"Games (rows): {len(df):,}")

    player_col = "Player ID" if "Player ID" in df.columns else "Player" if "Player" in df.columns else None
    if player_col:
        players = df[player_col].dropna().astype(str).str.strip()
        players = players[players != ""]
        lines.append(f"Unique players ({player_col}): {players.nunique():,}")

    return "\n".join(lines)


def print_slice(df: pd.DataFrame, limit: int | None = None) -> None:
    if limit is None:
        with pd.option_context("display.max_rows", None, "display.max_columns", None, "display.width", 200):
            print(df.to_string(index=False))
        return
    if limit >= 0:
        view = df.head(limit)
        print(view.to_string(index=False))
        return
    view = df.tail(abs(limit))
    print(view.to_string(index=False))


class CavInspector:
    def __init__(self) -> None:
        self.source_label: str | None = None
        self.source_path: Path | None = None
        self.df: pd.DataFrame | None = None

    @property
    def has_data(self) -> bool:
        return self.df is not None

    def load_path(self, path: Path, *, label: str | None = None) -> None:
        resolved = path.expanduser().resolve()
        if resolved.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise ValueError(f"Not a supported csv/parquet file: {resolved}")
        if not resolved.is_file():
            raise FileNotFoundError(resolved)
        self.df = load_dataframe(resolved)
        self.source_path = resolved
        self.source_label = label or resolved.name

    def summary(self) -> str:
        if self.df is None:
            return "No file loaded."
        return slice_summary(self.df, source_label=self.source_label)

    def select_columns(self, tokens: list[str]) -> None:
        if self.df is None:
            raise RuntimeError("No file loaded.")
        columns = resolve_column_tokens(list(self.df.columns), tokens)
        self.df = self.df.loc[:, columns]

    def unique_slice(self, tokens: list[str]) -> None:
        if self.df is None:
            raise RuntimeError("No file loaded.")
        columns = resolve_column_tokens(list(self.df.columns), tokens)
        self.df = self.df.drop_duplicates(subset=columns).loc[:, columns]

    def filter_slice(self, column_token: str, needle: str) -> None:
        if self.df is None:
            raise RuntimeError("No file loaded.")
        column = resolve_column_token(list(self.df.columns), column_token)
        before = len(self.df)
        self.df = filter_substring(self.df, column, needle)
        matched = len(self.df)
        print(f"Filter {column!r} contains {needle!r}: {matched:,} / {before:,} rows")

    def print_help(self) -> None:
        print(
            "\n".join(
                [
                    "",
                    "CAV inspector — CSV / Parquet data slice tool",
                    "",
                    "Global:",
                    "  l          load a file from the preset list",
                    "  a          load a file by full path (adds to preset list)",
                    "  i          inspect the loaded slice",
                    "  h          show this help",
                    "  q          quit",
                    "",
                    "Inspect mode (after i):",
                    "  h          show inspect commands",
                    "  s          select columns by id or name",
                    "  s 1,4,12   select columns directly",
                    "  f 2 Feller filter rows where column contains substring",
                    '  f Player "Feller"  filter by column name (quote if needed)',
                    "  d          show current slice dimensions",
                    "  u          unique rows for selected columns",
                    "  p          print full current slice",
                    "  p 10       print first 10 rows",
                    "  p -10      print last 10 rows",
                    "  b          back to global commands",
                    "",
                ]
            )
        )

    def print_inspect_help(self) -> None:
        print(
            "\n".join(
                [
                    "",
                    "Inspect commands:",
                    "  h          show this help",
                    "  s          select columns by id or name",
                    "  s 1,4,12   select columns directly",
                    "  f 2 Feller filter rows where column contains substring",
                    '  f Player "Feller"  filter by column name (quote if needed)',
                    "  d          show current slice dimensions",
                    "  u          unique rows for selected columns",
                    "  p          print full current slice",
                    "  p 10       print first 10 rows",
                    "  p -10      print last 10 rows",
                    "  b          back to global commands",
                    "",
                ]
            )
        )

    def show_load_menu(self) -> None:
        config = load_config()
        entries = config.get("files", [])
        print("\nLoad preset file:")
        if not entries:
            print("  (no presets configured — use 'a' to add one)")
        for index, entry in enumerate(entries[:9], start=1):
            label = entry.get("label", entry.get("path", "?"))
            path = entry.get("path", "?")
            exists = (REPO_ROOT / path).is_file() if not Path(path).is_absolute() else Path(path).is_file()
            marker = "" if exists else " [missing]"
            print(f"  {index}. {label}{marker}")
            print(f"     {path}")
        print("  a. load by full path")
        print("  b. back")
        print("  h. show commands")

    def handle_load(self, choice: str) -> None:
        choice = choice.strip().lower()
        if choice in {"", "b"}:
            return
        if choice == "h":
            self.print_help()
            return
        if choice == "a":
            self.handle_add_path()
            return
        if not choice.isdigit():
            print("Enter a number 1-9, 'a', or 'b'.")
            return
        index = int(choice)
        if index < 1 or index > 9:
            print("Enter a number between 1 and 9.")
            return
        config = load_config()
        entries = config.get("files", [])
        if index > len(entries):
            print(f"No preset at position {index}.")
            return
        entry = entries[index - 1]
        rel_path = entry["path"]
        path = Path(rel_path) if Path(rel_path).is_absolute() else REPO_ROOT / rel_path
        self.load_path(path, label=entry.get("label", path.name))
        print(self.summary())

    def handle_add_path(self) -> None:
        raw = input("Full path to csv/parquet: ").strip().strip('"')
        if not raw:
            return
        path = Path(raw)
        try:
            self.load_path(path)
        except (OSError, ValueError) as exc:
            print(f"Could not load file: {exc}")
            return
        default_label = path.stem.replace("_", " ")
        label = input(f"Label for preset list [{default_label}]: ").strip() or default_label
        add_file_to_config(label, path)
        self.source_label = label
        print(f"Added to presets and loaded: {label}")
        print(self.summary())

    def inspect_loop(self) -> None:
        if not self.has_data:
            print("Load a file first with 'l' or 'a'.")
            return
        print("\nInspect mode. Type 'h' for commands, 'b' to return.")
        while True:
            command = input("inspect> ").strip()
            if not command:
                continue
            lowered = command.casefold()
            if lowered in {"b", "back"}:
                return
            if lowered in {"h", "help", "?"}:
                self.print_inspect_help()
                continue

            parts = command.split(maxsplit=1)
            action = parts[0].casefold()
            arg = parts[1].strip() if len(parts) > 1 else ""

            try:
                if action == "s":
                    if arg:
                        tokens = [token.strip() for token in arg.split(",")]
                        self.select_columns(tokens)
                    else:
                        print(format_column_menu(list(self.df.columns)))
                        raw = input("Column ids or names (comma-separated): ").strip()
                        if not raw:
                            continue
                        tokens = [token.strip() for token in raw.split(",")]
                        self.select_columns(tokens)
                    print(self.summary())
                    continue

                if action == "d":
                    if self.df is None:
                        print("No file loaded.")
                        continue
                    print(f"Dimensions: {len(self.df):,} rows x {len(self.df.columns)} cols")
                    continue

                if action == "u":
                    if arg:
                        tokens = [token.strip() for token in arg.split(",")]
                        self.unique_slice(tokens)
                    else:
                        print(format_column_menu(list(self.df.columns)))
                        raw = input("Column ids or names (comma-separated): ").strip()
                        if not raw:
                            continue
                        tokens = [token.strip() for token in raw.split(",")]
                        self.unique_slice(tokens)
                    print(self.summary())
                    continue

                if action == "p":
                    limit: int | None
                    if not arg:
                        limit = None
                    else:
                        limit = int(arg)
                    if self.df is None:
                        print("No file loaded.")
                        continue
                    print_slice(self.df, limit=limit)
                    continue

                if action == "f":
                    if not arg:
                        print(format_column_menu(list(self.df.columns)))
                        raw = input('Filter as: <col_id_or_name> <substring>  (e.g. 2 "Feller"): ').strip()
                        if not raw:
                            continue
                        column_token, needle = parse_filter_args(raw)
                    else:
                        column_token, needle = parse_filter_args(arg)
                    self.filter_slice(column_token, needle)
                    print(self.summary())
                    continue

                print("Unknown inspect command. Use h for help.")
            except ValueError as exc:
                print(exc)

    def run(self) -> None:
        self.print_help()
        while True:
            try:
                command = input("cav> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if not command:
                continue
            lowered = command.casefold()
            if lowered in {"q", "quit", "exit"}:
                return
            if lowered in {"h", "help", "?"}:
                self.print_help()
                continue
            if lowered == "l":
                self.show_load_menu()
                choice = input("load> ").strip()
                self.handle_load(choice)
                continue
            if lowered == "a":
                self.handle_add_path()
                continue
            if lowered == "i":
                self.inspect_loop()
                continue
            print("Unknown command. Use l, a, i, h, or q.")


def main() -> int:
    CavInspector().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
