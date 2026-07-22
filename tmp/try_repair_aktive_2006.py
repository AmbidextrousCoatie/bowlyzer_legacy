from pathlib import Path

import xlrd
from python_calamine import CalamineWorkbook

src = Path(r"C:\tmp\bowlyzer\data\legacy_scrape\saison2006-07\allgemein\aktive_070630.xls")
data = src.read_bytes()
print("size", len(data), "mod512", len(data) % 512)
tmp = Path(r"C:\tmp\bowlyzer\data\aktive_070630_try.xls")


def try_read(label: str, blob: bytes) -> bool:
    tmp.write_bytes(blob)
    ok = False
    try:
        book = xlrd.open_workbook(str(tmp), ignore_workbook_corruption=True)
        print(label, "xlrd OK", book.nsheets, book.sheet_names()[:3])
        ok = True
    except Exception as exc:
        print(label, "xlrd FAIL", type(exc).__name__, str(exc)[:140])
    try:
        wb = CalamineWorkbook.from_path(str(tmp))
        print(label, "calamine OK", wb.sheet_names)
        ok = True
    except Exception as exc:
        print(label, "calamine FAIL", type(exc).__name__, str(exc)[:140])
    return ok


pad = (512 - (len(data) % 512)) % 512
for extra in [0, pad, pad + 512, pad + 1024, pad + 2048, pad + 4096, pad + 8192]:
    try_read(f"pad={extra}", data + b"\x00" * extra)
