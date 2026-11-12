# -*- coding: utf-8 -*-
"""补 2 期 Playbabes 泳装特刊（文件名无月份，gen_magazines 解析不了日期）。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_magazines as g  # noqa: E402

reg = g.load_registry()
by_folder, mags = g.build_index(reg)
mag = by_folder["pbs"]

CASES = [
    ("2025", "2025-05", "2025 年 5 月 · Swimsuit",
     g.ROOT_SRC / "PBS" / "2025" / "Playbabes_Special_Edition_-_Swimsuit_Issue_2025.pdf"),
    ("2026", "2026-05", "2026 年 5 月 · Swimsuit",
     g.ROOT_SRC / "PBS" / "2026" / "Playbabes_Special_Edition_-_Swimsuit_2026.pdf"),
]

for year, issue, label, pdf in CASES:
    if not pdf.exists():
        print("缺文件", pdf)
        continue
    rec = {
        "pdf": pdf, "mag": mag, "edition": "", "edition_slug": "",
        "issue": issue, "key": f"{issue}-swimsuit", "date": f"{issue}-01",
        "label": label, "pages": 0,
        "size": f"{pdf.stat().st_size / 1048576:.1f} MB",
    }
    fitz = g._fitz()
    with fitz.open(pdf) as doc:
        rec["pages"] = doc.page_count
    thumb_dir = g.OUT_THUMBS / mag["slug"] / rec["key"]
    ok = g.make_thumbs(pdf, thumb_dir)
    out = g.write_md(rec, mag)
    print(f"{rec['key']}: pages={rec['pages']} thumbs={ok} -> {out}")
