# -*- coding: utf-8 -*-
"""判断每期 PDF 里哪一页才是真正的封面，结果写 scripts/.cover_pages.json。

问题来源：Penthouse 2018-2021 的数字版在封面外面包了一张整页广告
（MyFreeCams、Gin 之类），直接取第 1 页就会把广告当封面。

  注：2026-11 已把这批源文件手动改成「第 1 页就是封面」，所以下面第 2 步
  现在不会命中，保留逻辑是为了以后遇到同类装订（广告包封面）能自动识别。

思路是「先看刊物习惯，再看单期」：
  1. 先扫全库每期前 4 页有没有条形码，统计每种刊物「首页无码、第 2 页有码」的比例。
  2. 比例超过 30% 的刊物判定为「封面被广告包着」，
     这类刊物逐期看：首页有码→首页；首页无码、第 2 页有码→第 2 页；否则首页。
  3. 其余刊物一律取第 1 页。

  只认「第 2 页」是刻意的：广告包只有一张，再往后（第 3、4 页）有条形码的多是
  内页广告或邮购页，跟着换就会把内页当封面。

  不用「有条形码就算封面」一刀切，是因为 Economist、New Yorker、Science 的封面
  本身不带条形码，而内页广告和目录页常常带，一刀切会把内页当封面。

用法：
    python scripts/detect_covers.py          # 全库（约 4 分钟）
"""
from __future__ import annotations

import collections
import json
import re
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pymupdf

HERE = Path(__file__).resolve().parent
SRC = Path(r"E:/迅雷下载/英文杂志/原文档")
OUT = HERE / ".cover_pages.json"
SCAN_PAGES = 4          # 前 4 页足够覆盖「广告 + 封面」的装订
WRAPPER_RATIO = 0.30    # 超过这个比例就认为该刊物封面被广告包着

_det = cv2.barcode.BarcodeDetector()


def has_barcode(page, zoom=0.6) -> bool:
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    ok, _ = _det.detect(cv2.cvtColor(arr, cv2.COLOR_RGB2BGR))
    return bool(ok)


def scan(pdfs):
    """返回 {相对路径: [每页是否有条形码]}"""
    out, t0 = {}, time.time()
    for k, p in enumerate(pdfs, 1):
        rel = str(p.relative_to(SRC))
        try:
            with pymupdf.open(p) as doc:
                out[rel] = [has_barcode(doc[i])
                            for i in range(min(SCAN_PAGES, doc.page_count))]
        except Exception as e:
            print(f"  [ERR] {rel}: {e}")
        if k % 100 == 0:
            print(f"  [{k}/{len(pdfs)}] {time.time() - t0:.0f}s", flush=True)
    return out


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    pdfs = sorted(SRC.rglob("*.pdf"))
    print(f"扫描 {len(pdfs)} 个 PDF 的前 {SCAN_PAGES} 页…")
    bc = scan(pdfs)

    # 刊物级：是否属于「封面被广告包着」的装订
    groups = collections.defaultdict(list)
    for rel, flags in bc.items():
        groups[rel.split("\\")[0]].append(flags)
    wrapper = {}
    for mag, rows in groups.items():
        n = len(rows)
        k = sum(1 for f in rows if len(f) > 1 and not f[0] and f[1])
        wrapper[mag] = (k / n > WRAPPER_RATIO) if n else False
        print(f"  {mag:6s} {n:3d} 期  p1 无码/ p2 有码 {k:3d}  "
              f"{'→ 按包装装订处理' if wrapper[mag] else ''}")

    res, moved = {}, 0
    for rel, flags in bc.items():
        mag = rel.split("\\")[0]
        page, why = 0, "p1"
        if wrapper[mag] and len(flags) > 1 and not flags[0] and flags[1]:
            page, why = 1, "ad-wrapper-p2"
        res[rel] = {"page": page, "why": why}
        if page:
            moved += 1
            print(f"  [p{page + 1}] {rel}")

    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n完成 {len(res)} 期，封面换页 {moved} 期")


if __name__ == "__main__":
    main()
