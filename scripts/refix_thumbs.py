# -*- coding: utf-8 -*-
"""重做封面 / 缩略图 / 内页预览，只动图片，不改 md。

两个问题：
  1. 部分 PDF 在封面之前放了整页广告，原来一律取第 1 页，结果封面是广告。
     → 用 detect_covers.py 的结论（scripts/.cover_pages.json）挑真正封面页。
  2. 内页预览按固定百分比取页（18%/38%/56%/74%），经常正好落在整页广告上。
     → 改为在目标位置附近搜一圈，挑「文字量接近本期文章页水平、又不含广告用语」的页。

用法：
    python scripts/refix_thumbs.py --only penthouse
    python scripts/refix_thumbs.py                 # 全站重做（约 30-50 分钟）
    python scripts/refix_thumbs.py --only maxim --force-previews
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from pathlib import Path

import pymupdf
from PIL import Image

HERE = Path(__file__).resolve().parent.parent
SRC = Path(r"E:/迅雷下载/英文杂志/原文档")
CONTENT = HERE / "content" / "magazines"
THUMBS = HERE / "static" / "thumbs" / "magazines"

COVER_MAX, THUMB_MAX, PREVIEW_MAX = (520, 730), (320, 450), (440, 600)
COVER_Q, THUMB_Q, PREVIEW_Q = 82, 80, 80
IMG_EXT = "webp"

RE_AD = re.compile(
    r"advertis|advertorial|to advertise|subscribe now|subscription offer|"
    r"scan (this|the) qr|order now|call \d|visit us at|find us on|"
    r"follow us on|download the app", re.I)


def page_stats(page):
    t = page.get_text()
    flat = " ".join(t.split())
    chars = len(re.sub(r"\s", "", t))
    return chars, bool(RE_AD.search(flat))


def render(doc, idx, out: Path, box, quality):
    page = doc[idx]
    r = page.rect
    zoom = min(box[0] / r.width, box[1] / r.height)
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "WEBP", quality=quality, method=6)


def pick_previews(doc, cover_idx, n, count=4):
    """在版面中间区域挑 4 页：文字量接近本期文章页，且不像广告。"""
    lo = min(cover_idx + 3, n - 1)
    hi = max(n - 4, lo + 1)
    span = hi - lo
    if span < count * 2:
        lo, hi, span = min(cover_idx + 1, n - 1), n - 1, max(n - 1 - cover_idx, 1)

    # 先用 24 个采样点估本期「典型文章页」的文字量
    sample = sorted({lo + int(span * i / 24) for i in range(24)})
    vals = []
    for i in sample:
        c, _ = page_stats(doc[i])
        vals.append(c)
    p75 = sorted(vals)[int(len(vals) * 0.75)] if vals else 500
    target = max(400, min(p75, 3000))

    picks = []
    for frac in (0.2, 0.4, 0.6, 0.8):
        base = lo + int(span * frac)
        best, best_s = None, -9e9
        for d in range(0, 11):
            for cand in ((base + d, base - d) if d else (base,)):
                if not (lo <= cand <= hi) or cand in picks or cand >= n:
                    continue
                chars, ad = page_stats(doc[cand])
                if ad:
                    continue
                s = 1 - abs(chars - target) / (target + 1)
                if chars < 120 and target >= 600:
                    s -= 2.0                      # 几乎无文字：多半是广告或纯图
                s += 0.3 * (1 - d / 11)           # 尽量贴近目标位置，保证四张分散
                if s > best_s:
                    best, best_s = cand, s
        if best is None:                          # 整段都是广告，退回原位置
            best = min(max(base, lo), hi)
            while best in picks and best < hi:
                best += 1
        picks.append(best)
    return sorted(picks)


def load_md_map():
    """md 文件 → (slug, key, 文件名)。"""
    out = []
    for p in sorted(CONTENT.glob("*/*.md")):
        if p.name == "_index.md":
            continue
        t = p.read_text(encoding="utf-8")
        m = re.search(r'file_name:[ ]*"([^"]+)"', t)
        if not m:
            continue
        out.append((p.parent.name, p.stem, m.group(1)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="只处理指定刊物 slug，逗号分隔")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--force", action="store_true", help="已有图片也重做")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    covers = json.loads((HERE / "scripts" / ".cover_pages.json").read_text(encoding="utf-8"))
    by_name = {p.name: p for p in SRC.rglob("*.pdf")}
    only = {s.strip() for s in args.only.split(",") if s.strip()}

    items = [x for x in load_md_map() if not only or x[0] in only]
    if args.limit:
        items = items[:args.limit]

    t0 = time.time()
    done = skipped = moved = 0
    for i, (slug, key, fname) in enumerate(items, 1):
        out_dir = THUMBS / slug / key
        if not args.force and (out_dir / "cover.webp").exists() and (out_dir / "p4.webp").exists():
            skipped += 1
            continue
        pdf = by_name.get(fname)
        if not pdf:
            print(f"  [miss] {slug}/{key} {fname}")
            continue
        rel = str(pdf.relative_to(SRC))
        cidx = covers.get(rel, {}).get("page", 0)
        try:
            with pymupdf.open(pdf) as doc:
                n = doc.page_count
                if n == 0:
                    continue
                cidx = min(cidx, n - 1)
                render(doc, cidx, out_dir / f"cover.{IMG_EXT}", COVER_MAX, COVER_Q)
                render(doc, cidx, out_dir / f"thumb.{IMG_EXT}", THUMB_MAX, THUMB_Q)
                for k, idx in enumerate(pick_previews(doc, cidx, n), start=1):
                    render(doc, idx, out_dir / f"p{k}.{IMG_EXT}", PREVIEW_MAX, PREVIEW_Q)
        except Exception as e:
            print(f"  [ERR] {slug}/{key}: {e}")
            continue
        done += 1
        if cidx:
            moved += 1
        if i % 20 == 0 or i == len(items):
            print(f"  [{i}/{len(items)}] 重做 {done}（其中封面换页 {moved}）跳过 {skipped} "
                  f"{time.time() - t0:.0f}s", flush=True)

    print(f"\n完成：重做 {done} 期，封面换页 {moved} 期，跳过 {skipped} 期，"
          f"耗时 {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
