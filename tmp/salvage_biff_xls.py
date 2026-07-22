"""Salvage rows from a truncated BIFF8 Workbook stream (corrupt OLE .xls)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# BIFF record types
BOF = 0x0809
EOF = 0x000A
SST = 0x00FC
CONTINUE = 0x003C
LABELSST = 0x00FD
LABEL = 0x0204
NUMBER = 0x0203
RK = 0x027E
MULRK = 0x00BD
BLANK = 0x0201
ROW = 0x0208
DIMENSIONS = 0x0200
XF = 0x00E0


def _u16(data: bytes, off: int) -> int:
    return int.from_bytes(data[off : off + 2], "little")


def _u32(data: bytes, off: int) -> int:
    return int.from_bytes(data[off : off + 4], "little")


def _parse_sst(payload: bytes) -> List[str]:
    """Parse shared string table including CONTINUE fragments already concatenated."""
    if len(payload) < 8:
        return []
    # unique + total
    unique = _u32(payload, 0)
    strings: List[str] = []
    pos = 8
    while len(strings) < unique and pos < len(payload):
        if pos + 3 > len(payload):
            break
        char_count = _u16(payload, pos)
        flags = payload[pos + 2]
        pos += 3
        rich = 0
        phonetic = 0
        if flags & 0x08:
            if pos + 2 > len(payload):
                break
            rich = _u16(payload, pos)
            pos += 2
        if flags & 0x04:
            if pos + 4 > len(payload):
                break
            phonetic = _u32(payload, pos)
            pos += 4
        byte_len = char_count * (2 if flags & 0x01 else 1)
        if pos + byte_len > len(payload):
            # truncated string — stop
            break
        raw = payload[pos : pos + byte_len]
        pos += byte_len
        if flags & 0x01:
            text = raw.decode("utf-16le", errors="replace")
        else:
            text = raw.decode("latin-1", errors="replace")
        if rich:
            pos += rich * 4
        if phonetic:
            pos += phonetic
        strings.append(text)
    return strings


def iter_biff_records(data: bytes):
    pos = 0
    n = len(data)
    while pos + 4 <= n:
        rtype = _u16(data, pos)
        rlen = _u16(data, pos + 2)
        pos += 4
        if pos + rlen > n:
            # truncated record — yield partial and stop
            yield rtype, data[pos:n]
            break
        yield rtype, data[pos : pos + rlen]
        pos += rlen
        if rtype == EOF:
            break


def extract_cells_from_workbook_stream(data: bytes) -> Tuple[List[str], Dict[Tuple[int, int], Any]]:
    """Return (sst, cells{(row,col): value}) from a (possibly truncated) BIFF8 stream."""
    sst: List[str] = []
    cells: Dict[Tuple[int, int], Any] = {}
    pending_sst = bytearray()
    in_sst = False

    for rtype, payload in iter_biff_records(data):
        if rtype == SST:
            pending_sst = bytearray(payload)
            in_sst = True
            continue
        if rtype == CONTINUE and in_sst:
            pending_sst.extend(payload)
            continue
        if in_sst and rtype != CONTINUE:
            sst = _parse_sst(bytes(pending_sst))
            in_sst = False
            pending_sst = bytearray()

        if rtype == LABELSST and len(payload) >= 10:
            row, col = _u16(payload, 0), _u16(payload, 2)
            idx = _u32(payload, 6)
            if 0 <= idx < len(sst):
                cells[(row, col)] = sst[idx]
            continue
        if rtype == LABEL and len(payload) >= 8:
            row, col = _u16(payload, 0), _u16(payload, 2)
            # XF at 4, then char count + string
            if len(payload) < 9:
                continue
            nchars = _u16(payload, 6)
            flags = payload[8] if len(payload) > 8 else 0
            # simplified: often latin-1 without flags in older; BIFF8 has flags
            text_start = 8
            # BIFF8 LABEL uses unicode flags like SST
            if len(payload) > 9:
                flags = payload[8]
                text_start = 9
                byte_len = nchars * (2 if flags & 1 else 1)
                raw = payload[text_start : text_start + byte_len]
                text = raw.decode("utf-16le" if flags & 1 else "latin-1", errors="replace")
            else:
                text = ""
            cells[(row, col)] = text
            continue
        if rtype == NUMBER and len(payload) >= 14:
            import struct

            row, col = _u16(payload, 0), _u16(payload, 2)
            value = struct.unpack_from("<d", payload, 6)[0]
            cells[(row, col)] = value
            continue
        if rtype == RK and len(payload) >= 10:
            row, col = _u16(payload, 0), _u16(payload, 2)
            rk = _u32(payload, 6)
            cells[(row, col)] = _decode_rk(rk)
            continue

    if in_sst and pending_sst:
        sst = _parse_sst(bytes(pending_sst))

    return sst, cells


def _decode_rk(rk: int) -> float:
    div100 = bool(rk & 1)
    if rk & 2:
        value = float(rk >> 2)
    else:
        import struct

        value = struct.unpack("<d", struct.pack("<I", 0) + struct.pack("<I", rk & 0xFFFFFFFC))[0]
    return value / 100.0 if div100 else value


def cells_to_matrix(cells: Dict[Tuple[int, int], Any]) -> List[List[Any]]:
    if not cells:
        return []
    max_r = max(r for r, _ in cells)
    max_c = max(c for _, c in cells)
    matrix = [[None for _ in range(max_c + 1)] for _ in range(max_r + 1)]
    for (r, c), val in cells.items():
        matrix[r][c] = val
    return matrix


def salvage_xls_to_matrix(path: Path) -> List[List[Any]]:
    import olefile

    with olefile.OleFileIO(str(path)) as ole:
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
    _, cells = extract_cells_from_workbook_stream(data)
    return cells_to_matrix(cells)


if __name__ == "__main__":
    import pandas as pd

    src = Path(r"C:\tmp\bowlyzer\data\legacy_scrape\saison2006-07\allgemein\aktive_070630_fresh.xls")
    matrix = salvage_xls_to_matrix(src)
    print("rows", len(matrix), "cols", len(matrix[0]) if matrix else 0)
    for row in matrix[:6]:
        print(row[:10])
    # find header
    for i, row in enumerate(matrix[:20]):
        vals = [str(v) for v in row if v is not None]
        if any("EDV" in v.upper() for v in vals) or any("Pass" in v for v in vals):
            print("header row", i, row[:12])
