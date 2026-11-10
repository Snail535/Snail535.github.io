# -*- coding: utf-8 -*-
"""把自动创建分享得到的 shares.json 转成 fill_downloads.py 能吃的 links.csv。

shares.json 结构（由夸克客户端自动化脚本产出）：
    {"playboy/2025-12-africa": {"url": "https://pan.quark.cn/s/xxx", "pwd": "",
                                "name": "PLBAF2512.jpg", "path": "Playboy/2025/Africa", ...}, ...}

用法：
    python scripts/shares_to_links.py <shares.json> -o links.csv
    python scripts/fill_downloads.py links.csv
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
CONTENT = HERE / "content" / "magazines"


def issue_meta():
    """key -> (刊物名, 期次文案)，用于清单里备注，方便人工核对。"""
    out = {}
    for md in CONTENT.glob("*/*.md"):
        if md.name == "_index.md":
            continue
        text = md.read_text(encoding="utf-8")

        def grab(name):
            import re
            m = re.search(rf'^{name}:\s*"?(.*?)"?\s*$', text, re.M)
            return m.group(1) if m else ""

        out[f"{md.parent.name}/{md.stem}"] = (grab("magazine"), grab("issue_label"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("shares", help="shares.json 路径")
    ap.add_argument("-o", "--out", default="links.csv")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    data = json.loads(Path(args.shares).read_text(encoding="utf-8"))
    meta = issue_meta()

    rows, bad = [], []
    for key, v in data.items():
        url = (v.get("url") or "").strip()
        if not url.startswith("http"):
            bad.append(key)
            continue
        mag, label = meta.get(key, ("", ""))
        if not mag:
            bad.append(key)          # 站点没有这一期
            continue
        rows.append((key, mag, label, v.get("name", ""), url, v.get("pwd", "")))

    rows.sort(key=lambda r: (r[1].lower(), r[0]))
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(("key", "magazine", "issue", "file_name", "url", "pwd"))
    w.writerows(rows)
    Path(args.out).write_text(buf.getvalue(), encoding="utf-8-sig")

    print(f"{args.out}：{len(rows)} 条可写入"
          f"{f'，{len(bad)} 条对不上站点期次' if bad else ''}")
    for k in bad[:20]:
        print(f"  [skip] {k}")


if __name__ == "__main__":
    main()
