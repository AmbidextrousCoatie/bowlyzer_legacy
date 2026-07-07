"""Compare 2016+ BM/SBM/NBM PDF layout stability."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

INPUT = Path(r"C:\tmp\bowlyzer\data\tournaments\input")

FILES_2016_PLUS = sorted(
    p for p in INPUT.glob("bm201[6-9]*.pdf")
    if p.name not in {"bm2012_sbm_h_erg.pdf"}
)


@dataclass
class PdfProfile:
    name: str
    pages: int
    size: int
    header_lines: list[str]
    footer_lines: list[str]
    first_player_snippet: str
    round_labels: set[str]
    has_player_id: bool
    player_count_guess: int
    text_chars: int


ROUND_PATTERNS = [
    r"Vorrunde",
    r"Zw-?Runde",
    r"Zwischenlauf",
    r"Finalrunde",
    r"Finale",
    r"Rd\.\d",
]


def profile_pdf(path: Path) -> PdfProfile:
    import fitz

    doc = fitz.open(path)
    page_count = doc.page_count
    all_text = "\n".join(doc[i].get_text("text") for i in range(page_count))
    first_page = doc[0].get_text("text")
    last_page = doc[page_count - 1].get_text("text")

    lines = [ln.strip() for ln in first_page.splitlines() if ln.strip()]
    header_lines = lines[:12]

    last_lines = [ln.strip() for ln in last_page.splitlines() if ln.strip()]
    footer_lines = last_lines[-8:]

    round_labels: set[str] = set()
    for pat in ROUND_PATTERNS:
        round_labels.update(re.findall(pat, all_text, flags=re.I))

    # crude player block: first rank+name pattern
    m = re.search(
        r"(\d+\.\s+[A-Za-zÄÖÜäöüß].{5,60}\n(?:.*\n){1,20}?Finalrunde\s+\d+)",
        first_page,
        flags=re.I,
    )
    snippet = m.group(1)[:500] if m else first_page[:600]

    ids = re.findall(r"\n(\d{5})\n", all_text)
    ranks = re.findall(r"^(\d+)\.\s", all_text, flags=re.M)

    doc.close()
    return PdfProfile(
        name=path.name,
        pages=page_count,
        size=path.stat().st_size,
        header_lines=header_lines,
        footer_lines=footer_lines,
        first_player_snippet=snippet,
        round_labels=round_labels,
        has_player_id=bool(ids),
        player_count_guess=len(set(ranks)),
        text_chars=len(all_text),
    )


def main() -> None:
    profiles = [profile_pdf(p) for p in FILES_2016_PLUS]

    print("2016+ PDF COMPARISON")
    print("=" * 80)
    for p in profiles:
        print(f"\n## {p.name}")
        print(f"   pages={p.pages}  size={p.size:,}  chars={p.text_chars:,}  players~={p.player_count_guess}")
        print(f"   round labels: {sorted(p.round_labels)}")
        print(f"   has 5-digit IDs: {p.has_player_id}")
        print("   HEADER:")
        for ln in p.header_lines:
            print(f"     | {ln}")
        print("   FOOTER (last page):")
        for ln in p.footer_lines:
            print(f"     | {ln}")
        print("   FIRST PLAYER SNIPPET:")
        for ln in p.first_player_snippet.splitlines()[:14]:
            print(f"     | {ln}")

    # structural invariants
    print("\n" + "=" * 80)
    print("STRUCTURAL INVARIANTS (2016+)")
    keys = ["Vorrunde", "Zw", "Finalrunde"]
    for p in profiles:
        has_v = any("Vorrunde" in x for x in p.round_labels)
        has_z = any("Zw" in x or "Zwischen" in x for x in p.round_labels)
        has_f = any("Final" in x for x in p.round_labels)
        hdr = " ".join(p.header_lines[:4])
        print(
            f"  {p.name:35} V={has_v} Z={has_z} F={has_f}  "
            f"hdr_date={bool(re.search(r'\\d{1,2}\\.', hdr))}"
        )


if __name__ == "__main__":
    main()
