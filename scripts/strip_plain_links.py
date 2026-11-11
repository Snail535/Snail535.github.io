#!/usr/bin/env python3
"""把 md 里的明文网盘链接替换成 has_download 标记。

链接本体已经进了 Cloudflare KV（见 build_kv_links.py），仓库里不再保留明文，
否则任何人 git clone 就能拿到全部 866 条。

替换规则
  download_url: "https://pan.quark.cn/s/xxxx"   ->  has_download: true
  download_url: ""                              ->  整行删除

幂等：已经是 has_download 的文件会被跳过，可重复执行。

用法
  python scripts/strip_plain_links.py --dry-run   # 只看会改什么
  python scripts/strip_plain_links.py             # 实际写入
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content" / "magazines"

RE_WITH_URL = re.compile(r'^download_url:\s*["\']?https?://\S+["\']?\s*$', re.M)
RE_EMPTY = re.compile(r'^download_url:\s*["\']{2}\s*$\n?', re.M)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只统计不写文件")
    args = ap.parse_args()

    filled = empty = skipped = 0
    samples: list[str] = []

    for md in sorted(CONTENT.glob("*/*.md")):
        text = md.read_text(encoding="utf-8")
        if "has_download:" in text:
            skipped += 1
            continue

        has_filled = bool(RE_WITH_URL.search(text))
        has_empty = bool(RE_EMPTY.search(text))
        if not has_filled and not has_empty:
            continue

        if has_filled:
            new = RE_WITH_URL.sub("has_download: true", text)
            filled += 1
        else:
            new = RE_EMPTY.sub("", text)
            empty += 1

        if len(samples) < 3:
            before = [l for l in text.splitlines() if l.startswith("download_url")][:1]
            after = [l for l in new.splitlines() if l.startswith("has_download")][:1]
            samples.append(f"{md.relative_to(ROOT)}\n    - {before}\n    + {after}")

        if not args.dry_run:
            md.write_text(new, encoding="utf-8")

    print(f"{'[预演] ' if args.dry_run else ''}有链接改标记 {filled} 个，空链接删行 {empty} 个，已处理跳过 {skipped} 个")
    for s in samples:
        print(s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
