"""Quick analysis of BM/SBM/NBM PDF exports."""
from __future__ import annotations

from pathlib import Path

PDFS = [
    Path(r"C:\tmp\bowlyzer\data\tournaments\input\bm2019_akt_sb_he_erg.pdf"),
    Path(r"C:\tmp\bowlyzer\data\tournaments\input\bm2016_sb_he_erg.pdf"),
    Path(r"C:\tmp\bowlyzer\data\tournaments\input\bm2012_sbm_h_erg.pdf"),
    Path(r"C:\tmp\bowlyzer\data\tournaments\input\bm2009_sb_da_erg.pdf"),
]


def main() -> None:
    import fitz  # pymupdf

    for path in PDFS:
        print("=" * 70)
        print(f"FILE: {path.name} ({path.stat().st_size:,} bytes)")
        doc = fitz.open(path)
        print(f"Pages: {doc.page_count}")

        for i in range(doc.page_count):
            page = doc[i]
            text = page.get_text("text")
            blocks = page.get_text("blocks")
            tables = []
            try:
                tables = page.find_tables().tables
            except Exception as exc:
                tables_err = str(exc)
            else:
                tables_err = None

            print(f"\n--- Page {i + 1} ---")
            print(f"  text chars: {len(text)}")
            print(f"  text blocks: {len(blocks)}")
            if tables_err:
                print(f"  table detection error: {tables_err}")
            else:
                print(f"  detected tables: {len(tables)}")
                for ti, t in enumerate(tables[:3]):
                    data = t.extract()
                    print(f"  table {ti + 1}: {len(data)} rows x {len(data[0]) if data else 0} cols")
                    for row in data[:5]:
                        print(f"    {row}")
                    if len(data) > 5:
                        print("    ...")

            if i == 0:
                print("\n  FIRST PAGE TEXT (first 2500 chars):")
                print(text[:2500] or "(empty)")
        doc.close()


if __name__ == "__main__":
    main()
