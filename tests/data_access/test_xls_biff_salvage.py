"""BIFF salvage for truncated Aktive .xls workbooks."""

from __future__ import annotations

import struct

from data_access.xls_biff_salvage import (
    _MULRK,
    cells_to_dataframe,
    extract_cells_from_workbook_stream,
)


def _record(rtype: int, payload: bytes) -> bytes:
    return struct.pack("<HH", rtype, len(payload)) + payload


def test_extract_mulrk_and_labelsst_cells() -> None:
    # Minimal SST with one string
    sst_payload = struct.pack("<II", 1, 1)  # unique, total
    # unicode string "Baur": char_count=4, flags=0 (latin-1)
    sst_payload += struct.pack("<HB", 4, 0) + b"Baur"
    # LABELSST row=1 col=2 idx=0
    labelsst = struct.pack("<HHHI", 1, 2, 0, 0)
    # MULRK row=1 first_col=0: two RK values (EDV 16607, Pass 890124), last_col=1
    # RK integer encoding: (value << 2) | 2
    def rk_int(value: int) -> int:
        return (value << 2) | 2

    mulrk_body = b""
    for value in (16607, 890124):
        mulrk_body += struct.pack("<HI", 0, rk_int(value))  # XF + RK
    mulrk = struct.pack("<HH", 1, 0) + mulrk_body + struct.pack("<H", 1)

    stream = b"".join(
        [
            _record(0x0809, b"\x00" * 16),  # BOF workbook
            _record(0x00FC, sst_payload),
            _record(0x000A, b""),  # EOF globals
            _record(0x0809, b"\x00" * 16),  # BOF sheet
            _record(_MULRK, mulrk),
            _record(0x00FD, labelsst),
            _record(0x000A, b""),
        ]
    )
    cells = extract_cells_from_workbook_stream(stream)
    assert cells[(1, 0)] == 16607.0
    assert cells[(1, 1)] == 890124.0
    assert cells[(1, 2)] == "Baur"
    frame = cells_to_dataframe(cells)
    assert frame.shape[0] >= 2
