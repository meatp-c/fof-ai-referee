#!/usr/bin/env python3
"""Build the rule text files that fof.py needs for `rule <no>` and `search <term>`, from YOUR OWN PDFs.

No rule text ships with this kit (copyright GMT Games). Run this once with the PDFs you own:

    python3 tool/build_rules_index.py --rules "Series Rules 3rd Ed.pdf" \
        [--clarifications "Clarifications May 2025.pdf"] [--extra "Normandy Mission Book.pdf" ...]

Needs `pdftotext` (poppler-utils). It writes into data/:
    rulebook.txt                       rulebook in reading order (form feed = page break)
    rulebook_compact.txt               same without empty lines (fof.py quotes from this file)
    rule_index.json                    {rule: {"title", "page", "line_txt", "line_compact"}}
    clarifications_2025_05_compact.txt (optional) errata/clarifications, checked by `rule`
    <name>_compact.txt                 (optional) any further PDF, included in `search`
Files built by an earlier release under their German names are still read by fof.py.
"""

import argparse
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def pdf_to_text(pdf, out):
    subprocess.run(["pdftotext", str(pdf), str(out)], check=True)
    return out.read_text(encoding="utf-8", errors="replace")


def compact(text):
    return "\n".join(l for l in text.split("\n") if l.strip())


def build_index(txt, compact_lines):
    """Index rule headings like '6.4.2 Hit Effects' with page (form feeds) and line numbers."""
    pat = re.compile(r"^(\d{1,2}\.\d{1,2}(?:\.\d{1,2})?)\s+([A-Z][^\.]{2,80}?)\s*$")
    index, page, ln, toc_done = {}, 1, 0, False
    pos = {}
    for i, l in enumerate(compact_lines, 1):
        pos.setdefault(l.strip(), i)
    for line in txt.split("\n"):
        ln += 1
        page += line.count("\f")
        s = line.replace("\f", "").strip()
        if not s:
            continue
        if s.startswith("1.0 Introduction") and page >= 3:  # skip the table of contents
            toc_done = True
        if not toc_done:
            continue
        m = pat.match(s)
        if m and m.group(1) not in index:
            index[m.group(1)] = {
                "title": m.group(2).strip(),
                "page": page,
                "line_txt": ln,
                "line_compact": pos.get(s),
            }
    return index


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rules", required=True, help="Series Rules PDF")
    ap.add_argument("--clarifications", help="clarifications/errata PDF")
    ap.add_argument("--extra", nargs="*", default=[], help="further PDFs for `search` (mission books, player aids)")
    a = ap.parse_args()
    DATA.mkdir(exist_ok=True)
    txt = pdf_to_text(a.rules, DATA / "rulebook.txt")
    compact_text = compact(txt)
    (DATA / "rulebook_compact.txt").write_text(compact_text, encoding="utf-8")
    idx = build_index(txt, compact_text.split("\n"))
    (DATA / "rule_index.json").write_text(json.dumps(idx, indent=1, ensure_ascii=False), encoding="utf-8")
    print(len(idx), "rule headings indexed")
    if not idx:
        print(
            "WARNING: no headings found. The index expects lines like '6.4 Combat Resolution & Effects' after '1.0 Introduction'."
        )
    if a.clarifications:
        t = pdf_to_text(a.clarifications, DATA / "clarifications.txt")
        (DATA / "clarifications_2025_05_compact.txt").write_text(compact(t), encoding="utf-8")
    for p in a.extra:
        p = pathlib.Path(p)
        name = re.sub(r"[^a-z0-9]+", "_", p.stem.lower()).strip("_")
        t = pdf_to_text(p, DATA / f"{name}.txt")
        (DATA / f"{name}_compact.txt").write_text(compact(t), encoding="utf-8")
        print("added", name)


if __name__ == "__main__":
    sys.exit(main())
