# -*- coding: utf-8 -*-
"""预览图瘦身：JPEG → WebP，按实际展示尺寸重采样，并剔除网页根本不引用的图片。

背景：
- 原先从 PDF 渲染时封面 640 宽、内页 560 宽，而页面实际展示只有 260 / 约 180 px，
  像素量远超需要，static/thumbs 达 437MB。
- 换 WebP 同尺寸约省 20%，再按「2 倍于展示宽度」重采样，总体约省一半，
  页面观感不变（仍是 Retina 2x）。

规则：
- cover*.jpg   → 宽 520，q82
- thumb*.jpg   → 宽 320，q80
- p1-p4*.jpg   → 宽 440，q80
- 只保留 md 与 data/censored_previews.json 真正引用到的图片；
  旧命名遗留的整期目录不再复制（也就不会被推送）。

实现：先在新目录 static/thumbs.new 里生成整棵树，成功后整体换名，
      旧树挪到 static/.thumbs-old（已加入 .gitignore），避免逐张删除。

用法：
    python scripts/optimize_images.py --dry     # 只统计
    python scripts/optimize_images.py           # 生成 + 换名 + 改写 md
    python scripts/optimize_images.py --keep-old  # 换名后保留旧树
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
STATIC = HERE / "static"
THUMBS = STATIC / "thumbs"
NEW = STATIC / "thumbs.new"
OLD = STATIC / ".thumbs-old"
CONTENT = HERE / "content" / "magazines"
DATA = HERE / "data" / "censored_previews.json"

# 文件名前缀 → (目标宽度, WebP 质量)
SPEC = {"cover": (520, 82), "thumb": (320, 80), "preview": (440, 80)}


def spec_for(name: str):
    stem = name.rsplit(".", 1)[0]
    if stem.startswith("cover"):
        return SPEC["cover"]
    if stem.startswith("thumb"):
        return SPEC["thumb"]
    return SPEC["preview"]


def collect_refs():
    refs = set()
    for md in CONTENT.glob("*/*.md"):
        if md.name == "_index.md":
            continue
        text = md.read_text(encoding="utf-8")
        for m in re.finditer(r'^(?:  image|  thumb|preview[1-4]):\s*"([^"]+)"', text, re.M):
            refs.add(m.group(1))
    mapping = json.loads(DATA.read_text(encoding="utf-8")) if DATA.exists() else {}
    for k, v in mapping.items():
        refs.add(k)
        refs.add(v)
    return refs, mapping


def rel_of(url: str) -> str:
    """'/thumbs/magazines/a/b/cover.jpg' → 'magazines/a/b/cover.webp'"""
    return url.split("/thumbs/", 1)[-1].rsplit(".", 1)[0] + ".webp"


def build_one(job):
    url, rel = job
    from PIL import Image

    src = STATIC / url.lstrip("/")
    dst = NEW / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    width, quality = spec_for(src.name)

    if src.exists():
        old = src.stat().st_size
        try:
            im = Image.open(src)
            if im.mode != "RGB":
                im = im.convert("RGB")
            if width and im.width > width:
                im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
            im.save(dst, "WEBP", quality=quality, method=6)
            return (url, old, dst.stat().st_size, "")
        except Exception as e:
            return (url, old, 0, f"错误 {str(e)[:50]}")

    # 上一次跑到一半时已生成的 .webp（原 jpg 已被删掉）
    alt = src.with_suffix(".webp")
    if alt.exists():
        shutil.copy2(alt, dst)
        return (url, alt.stat().st_size, dst.stat().st_size, "沿用已转换")
    return (url, 0, 0, "缺失")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--keep-old", action="store_true")
    ap.add_argument("--jobs", type=int, default=8)
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    refs, mapping = collect_refs()
    urls = sorted(u for u in refs if u.endswith(".jpg"))
    on_disk = {"/" + p.relative_to(STATIC).as_posix()
               for p in (THUMBS / "magazines").rglob("*.jpg")}
    stale = sorted(on_disk - set(urls))

    print(f"引用到的图片 {len(urls)} 张；未被引用的 {len(stale)} 张（不复制、不推送）")
    if stale:
        by_dir = {}
        for u in stale:
            k = "/".join(u.split("/")[:4])
            by_dir[k] = by_dir.get(k, 0) + 1
        for d, c in sorted(by_dir.items()):
            print(f"    {d}  {c} 张")

    if args.dry:
        old = sum((STATIC / u.lstrip('/')).stat().st_size
                  for u in urls if (STATIC / u.lstrip('/')).exists())
        print(f"\n待转换 {old / 1048576:.0f} MB，将丢弃 "
              f"{sum((STATIC / u.lstrip('/')).stat().st_size for u in stale) / 1048576:.1f} MB")
        print("预演模式，未写文件")
        return

    if NEW.exists():
        shutil.rmtree(NEW)
    jobs = [(u, rel_of(u)) for u in urls]
    results = []
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        for i, r in enumerate(pool.map(build_one, jobs, chunksize=16), 1):
            results.append(r)
            if i % 1000 == 0:
                print(f"  {i}/{len(jobs)}", flush=True)

    old = sum(r[1] for r in results)
    new = sum(r[2] for r in results)
    bad = [r for r in results if r[3]]
    print(f"\n转换：{old / 1048576:.0f} MB → {new / 1048576:.0f} MB"
          f"（-{(1 - new / max(old, 1)) * 100:.0f}%）")
    for r in bad[:8]:
        print(f"  [注意] {r[0]} {r[3]}")
    if len(bad) > 8:
        print(f"  ……另有 {len(bad) - 8} 条")

    made = sum(1 for _ in NEW.rglob("*.webp"))
    print(f"新树 {made} 个文件，{sum(f.stat().st_size for f in NEW.rglob('*.webp')) / 1048576:.0f} MB")

    # 换名：旧树挪走，新树就位
    if OLD.exists():
        shutil.rmtree(OLD)
    THUMBS.rename(OLD)
    NEW.rename(THUMBS)
    print("已换名：static/thumbs → static/.thumbs-old，static/thumbs.new → static/thumbs")

    changed = 0
    for md in CONTENT.glob("*/*.md"):
        if md.name == "_index.md":
            continue
        text = md.read_text(encoding="utf-8")
        new_text = re.sub(r'^(  image|  thumb|preview[1-4]):\s*"([^"]+)\.jpg"',
                          r'\1: "\2.webp"', text, flags=re.M)
        if new_text != text:
            md.write_text(new_text, encoding="utf-8")
            changed += 1
    print(f"改写 md {changed} 个")

    if mapping:
        DATA.write_text(json.dumps(
            {k.replace(".jpg", ".webp"): v.replace(".jpg", ".webp")
             for k, v in mapping.items()}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"改写打码映射 {len(mapping)} 条")

    if not args.keep_old:
        print(f"旧树保留在 {OLD.name}（{sum(f.stat().st_size for f in OLD.rglob('*') if f.is_file()) / 1048576:.0f} MB），"
              f"确认无误后可删除")


if __name__ == "__main__":
    main()
