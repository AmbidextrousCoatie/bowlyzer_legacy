"""Salvage cell grids from truncated OLE/BIFF8 ``.xls`` workbooks (Aktive fallback)."""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any, Dict, Iterator, List, Sequence, Tuple

import pandas as pd

# BIFF record types
_BOF = 0x0809
_EOF = 0x000A
_SST = 0x00FC
_CONTINUE = 0x003C
_LABELSST = 0x00FD
_LABEL = 0x0204
_NUMBER = 0x0203
_RK = 0x027E
_MULRK = 0x00BD
_MULBLANK = 0x00BE


def _u16(data: bytes, off: int) -> int:
    return int.from_bytes(data[off : off + 2], "little")


def _u32(data: bytes, off: int) -> int:
    return int.from_bytes(data[off : off + 4], "little")


def _decode_rk(rk: int) -> float:
    div100 = bool(rk & 1)
    if rk & 2:
        value = float(rk >> 2)
    else:
        value = struct.unpack("<d", struct.pack("<II", 0, rk & 0xFFFFFFFC))[0]
    return value / 100.0 if div100 else value


def iter_biff_records(data: bytes) -> Iterator[Tuple[int, bytes]]:
    """Yield ``(record_type, payload)``; continues past workbook-global EOF into sheets."""
    pos = 0
    n = len(data)
    while pos + 4 <= n:
        rtype = _u16(data, pos)
        rlen = _u16(data, pos + 2)
        pos += 4
        if pos + rlen > n:
            yield rtype, data[pos:n]
            break
        yield rtype, data[pos : pos + rlen]
        pos += rlen


def _read_unicode_string(payload: bytes, offset: int) -> Tuple[str, int]:
    """Read a BIFF8 unicode string starting at ``offset``; return (text, new_offset)."""
    if offset + 3 > len(payload):
        return "", len(payload)
    char_count = _u16(payload, offset)
    flags = payload[offset + 2]
    pos = offset + 3
    rich = 0
    phonetic = 0
    if flags & 0x08:
        if pos + 2 > len(payload):
            return "", len(payload)
        rich = _u16(payload, pos)
        pos += 2
    if flags & 0x04:
        if pos + 4 > len(payload):
            return "", len(payload)
        phonetic = _u32(payload, pos)
        pos += 4
    byte_len = char_count * (2 if flags & 0x01 else 1)
    if pos + byte_len > len(payload):
        return "", len(payload)
    raw = payload[pos : pos + byte_len]
    pos += byte_len
    text = raw.decode("utf-16le" if flags & 0x01 else "latin-1", errors="replace")
    if rich:
        pos += rich * 4
    if phonetic:
        pos += phonetic
    return text, pos


def _parse_sst(payload: bytes) -> List[str]:
    if len(payload) < 8:
        return []
    unique = _u32(payload, 0)
    strings: List[str] = []
    pos = 8
    while len(strings) < unique and pos < len(payload):
        text, pos = _read_unicode_string(payload, pos)
        if text == "" and pos >= len(payload):
            break
        strings.append(text)
    return strings


def extract_cells_from_workbook_stream(data: bytes) -> Dict[Tuple[int, int], Any]:
    sst: List[str] = []
    cells: Dict[Tuple[int, int], Any] = {}
    pending_sst = bytearray()
    collecting_sst = False

    def flush_sst() -> None:
        nonlocal sst, pending_sst, collecting_sst
        if collecting_sst and pending_sst:
            sst = _parse_sst(bytes(pending_sst))
        pending_sst = bytearray()
        collecting_sst = False

    for rtype, payload in iter_biff_records(data):
        if rtype == _SST:
            flush_sst()
            pending_sst = bytearray(payload)
            collecting_sst = True
            continue
        if rtype == _CONTINUE and collecting_sst:
            # CONTINUE may restart with a string-flag byte when splitting mid-string;
            # for Aktive workbooks the common case is raw continuation of SST bytes.
            pending_sst.extend(payload)
            continue
        if collecting_sst and rtype != _CONTINUE:
            flush_sst()

        if rtype == _LABELSST and len(payload) >= 10:
            row, col = _u16(payload, 0), _u16(payload, 2)
            idx = _u32(payload, 6)
            if 0 <= idx < len(sst):
                cells[(row, col)] = sst[idx]
            continue
        if rtype == _LABEL and len(payload) >= 9:
            row, col = _u16(payload, 0), _u16(payload, 2)
            text, _ = _read_unicode_string(payload, 6)
            cells[(row, col)] = text
            continue
        if rtype == _NUMBER and len(payload) >= 14:
            row, col = _u16(payload, 0), _u16(payload, 2)
            cells[(row, col)] = struct.unpack_from("<d", payload, 6)[0]
            continue
        if rtype == _RK and len(payload) >= 10:
            row, col = _u16(payload, 0), _u16(payload, 2)
            cells[(row, col)] = _decode_rk(_u32(payload, 6))
            continue
        if rtype == _MULRK and len(payload) >= 6:
            row = _u16(payload, 0)
            first_col = _u16(payload, 2)
            # trailing last_col is 2 bytes; each cell is XF(2)+RK(4)=6 bytes
            if len(payload) < 8:
                continue
            last_col = _u16(payload, len(payload) - 2)
            body = payload[4 : len(payload) - 2]
            col = first_col
            pos = 0
            while col <= last_col and pos + 6 <= len(body):
                rk = _u32(body, pos + 2)
                cells[(row, col)] = _decode_rk(rk)
                pos += 6
                col += 1
            continue

    flush_sst()
    return cells


def cells_to_dataframe(cells: Dict[Tuple[int, int], Any]) -> pd.DataFrame:
    if not cells:
        return pd.DataFrame()
    max_r = max(r for r, _ in cells)
    max_c = max(c for _, c in cells)
    rows: List[List[Any]] = []
    for r in range(max_r + 1):
        rows.append([cells.get((r, c)) for c in range(max_c + 1)])
    return pd.DataFrame(rows)


def read_truncated_xls_via_ole_biff(path: Path) -> pd.DataFrame:
    """
    Read a corrupt/truncated OLE ``.xls`` by extracting the Workbook stream with
    ``olefile`` and walking BIFF8 records (tolerates missing trailing sectors).
    """
    import olefile

    with olefile.OleFileIO(str(path)) as ole:
        if not ole.exists("Workbook"):
            raise ValueError(f"no Workbook stream in {path.name}")
        stream = ole.openstream("Workbook")
        chunks: List[bytes] = []
        while True:
            try:
                chunk = stream.read(65536)
            except Exception:
                break
            if not chunk:
                break
            chunks.append(chunk)
        data = b"".join(chunks)
    if len(data) < 32:
        raise ValueError(f"Workbook stream too small in {path.name}")
    cells = extract_cells_from_workbook_stream(data)
    if not cells:
        raise ValueError(f"no BIFF cells recovered from {path.name}")
    return cells_to_dataframe(cells)
