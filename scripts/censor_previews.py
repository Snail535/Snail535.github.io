# -*- coding: utf-8 -*-
"""内页/封面预览图：内容识别 → 局部马赛克，生成「打码版」。

依赖（本机一次性安装）：
    pip install nudenet opencv-python-headless onnxruntime pillow numpy
模型随 nudenet 安装包自带（320n.onnx），不联网下载。

做法：
- 只扫描「时尚成人」分类的期次（其他刊物完全不动）
- 用模型找出裸露部位的框，只对这些框做像素化，画面其余部分保持清晰
- 打码版另存为 <原文件名>c.webp，原图保留
- 输出 data/censored_previews.json：原图 URL → 打码版 URL，模板据此替换

用法：
    python scripts/censor_previews.py --dry          # 只统计，不写文件
    python scripts/censor_previews.py                # 执行
    python scripts/censor_previews.py --force        # 已存在也重新生成
    python scripts/censor_previews.py --only playboy
    python scripts/censor_previews.py --strict       # 连「遮盖但贴身」的部位也打码
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
CONTENT = HERE / "content" / "magazines"
THUMBS = HERE / "static" / "thumbs" / "magazines"
DATA = HERE / "data" / "censored_previews.json"

# 明确属于「裸露」的标签。脸、脚、腹部、腋下等不打码，避免误杀。
SENSITIVE = {
    "BUTTOCKS_EXPOSED",
    "FEMALE_BREAST_EXPOSED",
    "FEMALE_GENITALIA_EXPOSED",
    "MALE_GENITALIA_EXPOSED",
    "ANUS_EXPOSED",
}
STRICT_EXTRA = {
    "FEMALE_BREAST_COVERED",
    "FEMALE_GENITALIA_COVERED",
    "BUTTOCKS_COVERED",
    "ANUS_COVERED",
}
IMAGES = ["cover.webp", "thumb.webp", "p1.webp", "p2.webp", "p3.webp", "p4.webp"]


def adult_issues():
    out = []
    for md in sorted(CONTENT.glob("*/*.md")):
        if md.name == "_index.md":
            continue
        if "时尚成人" not in md.read_text(encoding="utf-8"):
            continue
        out.append((md.parent.name, md.stem))
    return out


def url_of(p: Path) -> str:
    return "/" + p.relative_to(HERE / "static").as_posix()


def censored_path(p: Path) -> Path:
    return p.with_name(p.stem + "c.webp")


def mosaic(img, box, pad_ratio=0.06):
    """对一个框做像素化（缩小再最近邻放大），带一点外扩避免露边。"""
    from PIL import Image

    W, H = img.size
    x, y, w, h = box
    px, py = int(w * pad_ratio), int(h * pad_ratio)
    x0, y0 = max(0, x - px), max(0, y - py)
    x1, y1 = min(W, x + w + px), min(H, y + h + py)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return img
    patch = img.crop((x0, y0, x1, y1))
    # 颗粒要够粗：肤色均匀的区域细马赛克几乎看不出变化
    block = max(12, min(patch.size) // 5)
    small = patch.resize((max(2, patch.width // block), max(2, patch.height // block)),
                         Image.Resampling.BILINEAR)
    pixel = small.resize(patch.size, Image.Resampling.NEAREST)
    img.paste(pixel, (x0, y0))
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--threshold", type=float, default=0.25)
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    from nudenet import NudeDetector
    from PIL import Image

    labels = SENSITIVE | (STRICT_EXTRA if args.strict else set())
    detector = NudeDetector()

    issues = [(s, k) for s, k in adult_issues() if not args.only or s == args.only]
    print(f"待扫描 {len(issues)} 期，敏感标签 {len(labels)} 类，阈值 {args.threshold}")

    mapping, stats, label_count = {}, collections.Counter(), collections.Counter()
    flagged_img = scanned = 0

    for n, (slug, key) in enumerate(issues, 1):
        d = THUMBS / slug / key
        if not d.is_dir():
            continue
        for name in IMAGES:
            p = d / name
            if not p.exists():
                continue
            scanned += 1
            out = censored_path(p)
            if out.exists() and not args.force and not args.dry:
                mapping[url_of(p)] = url_of(out)
                flagged_img += 1
                continue
            try:
                hits = [h for h in detector.detect(str(p))
                        if h["class"] in labels and h["score"] >= args.threshold]
            except Exception as e:
                print(f"  [检测失败] {p.name} {slug}/{key}: {str(e)[:60]}")
                continue
            if not hits:
                continue
            for h in hits:
                label_count[h["class"]] += 1
            flagged_img += 1
            mapping[url_of(p)] = url_of(out)
            if args.dry:
                continue
            im = Image.open(p).convert("RGB")
            for h in hits:
                im = mosaic(im, h["box"])
            im.save(out, "WEBP", quality=86, method=6)
            stats[slug] += 1
        if n % 40 == 0:
            print(f"  ... {n}/{len(issues)}，已标记 {flagged_img} 张", flush=True)

    print(f"\n扫描 {scanned} 张图，命中敏感区域 {flagged_img} 张"
          f"（{flagged_img / max(scanned, 1) * 100:.1f}%）")
    for lab, c in label_count.most_common():
        print(f"  {lab:<28} {c}")
    if args.dry:
        print("\n预演模式，未写文件")
        return

    DATA.write_text(json.dumps(dict(sorted(mapping.items())), ensure_ascii=False, indent=1),
                    encoding="utf-8")
    print(f"\n已写 {DATA.name}：{len(mapping)} 条映射，"
          f"打码版图片 {sum(stats.values())} 张新生成")


if __name__ == "__main__":
    main()
