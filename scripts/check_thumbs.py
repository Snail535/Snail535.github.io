# -*- coding: utf-8 -*-
"""检查每期 md 引用的封面/预览图是否都存在，并统计换页情况。

用法：python scripts/check_thumbs.py
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content" / "magazines"
STATIC = ROOT / "static"


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    missing, total = [], 0
    for md in sorted(CONTENT.glob("*/*.md")):
        if md.name == "_index.md":
            continue
        total += 1
        t = md.read_text(encoding="utf-8")
        for m in re.finditer(r'"(/thumbs/magazines/[^"]+\.webp)"', t):
            if not (STATIC / m.group(1).lstrip("/")).exists():
                missing.append(f"{md.parent.name}/{md.name} → {m.group(1)}")
    print(f"期次 {total}，缺失图片 {len(missing)}")
    for x in missing[:30]:
        print("  ", x)


if __name__ == "__main__":
    main()
