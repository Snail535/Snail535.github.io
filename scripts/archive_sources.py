# -*- coding: utf-8 -*-
"""把杂志 PDF 源文件整理成统一的三层结构：<刊物>/<年份>/<版本>/

老刊（FOR、ReadersDigest 等）本来就是 <刊物>/<年份>/<国家>/，
新下载的图种包解压出来是平铺的 <刊名 年份>/*.pdf，这里统一收拢。

版本目录 = 国家/地区（USA、SouthAfrica…）；没有国家时用专题名
（ArtisticNude、Letters…）；两者都没有就直接 <刊物>/<年份>/。

用法：
    python scripts/archive_sources.py --dry     # 只看会怎么移动
    python scripts/archive_sources.py           # 真正移动（同盘 rename，瞬间完成）
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("gen", HERE / "gen_magazines.py")
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

SRC = gen.ROOT_SRC


def mag_dirname(mag):
    """源文件目录名：优先用注册表里的第一个 folders 名，保持与老刊一致。"""
    dirs = mag.get("folders") or []
    return dirs[0] if dirs else mag["name"]


def tag_of(text):
    """USA / South Africa / Artistic Nude → 目录名（USA / SouthAfrica / ArtisticNude）。"""
    if not text:
        return ""
    if text.lower() == "black and white":
        return "BlackWhite"
    return "".join(w[:1].upper() + w[1:] for w in text.split())


def plan():
    reg = gen.load_registry()
    by_folder, mags = gen.build_index(reg)
    editions = gen.build_editions(reg)

    moves, skipped = [], 0
    for pdf in sorted(SRC.rglob("*.pdf")):
        rel = pdf.relative_to(SRC)
        # 只收拢平铺在顶层目录里的文件（<刊名 年份>/x.pdf）；
        # 已经是 <刊物>/<年份>/… 的老刊结构不动。
        if len(rel.parts) != 2:
            skipped += 1
            continue
        mag = gen.match_mag(by_folder, rel.parts[0])
        if not mag:
            skipped += 1
            continue

        pub_part, date_part = gen.split_publication_and_date(pdf.stem)
        parsed = gen.parse_date_part(date_part)
        if not parsed:
            skipped += 1
            continue
        y = parsed[1][0]

        edition = gen.detect_edition(pub_part, editions)
        if not edition:
            for part in rel.parts[1:-1]:
                edition = gen.detect_edition(part, editions)
                if edition:
                    break
        variant = gen.detect_variant(pub_part, date_part, mag, edition)

        tag = tag_of(edition or variant)
        target_dir = SRC / mag_dirname(mag) / f"{y:04d}"
        if tag:
            target_dir = target_dir / tag
        target = target_dir / pdf.name

        if target.resolve() == pdf.resolve():
            skipped += 1
        else:
            moves.append((pdf, target))
    return moves, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    moves, skipped = plan()
    print(f"需要移动 {len(moves)} 个文件，已就位 {skipped} 个\n")

    if args.dry:
        for src, dst in moves[:40]:
            print(f"  {src.relative_to(SRC)}\n    → {dst.relative_to(SRC)}")
        if len(moves) > 40:
            print(f"  …… 其余 {len(moves) - 40} 个略")
        return

    done = 0
    for src, dst in moves:
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():                       # 同名文件已存在就不覆盖
                print(f"  [skip] 目标已存在：{dst.relative_to(SRC)}")
                continue
            src.replace(dst)                       # 同盘 rename，不占额外空间
            done += 1
        except Exception as e:
            print(f"  [ERR] {src.name}: {e}")
    print(f"\n已移动 {done} 个文件")

    # 清掉搬空后的旧目录（只删空目录，非空会失败，天然安全）
    for d in sorted(SRC.rglob("*"), key=lambda p: -len(p.parts)):
        if not d.is_dir():
            continue
        try:
            d.rmdir()
            print(f"  [rmdir] {d.relative_to(SRC)}")
        except OSError:
            pass


if __name__ == "__main__":
    main()
