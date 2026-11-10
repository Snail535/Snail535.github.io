#!/usr/bin/env python3
"""把各期网盘链接导出成 Cloudflare KV 用的数据。

Worker 上线后，链接只存在 KV 里，仓库和页面 HTML 都不再保留明文。

用法
  python scripts/build_kv_links.py            # 生成 scripts/.links_kv.json
  python scripts/build_kv_links.py --bulk     # 额外生成 wrangler bulk put 用的数组
  python scripts/build_kv_links.py --check    # 只校验 key 是否齐全/冲突

key 规则必须与 layouts/magazines/single.html 一致：
  <magazine_slug>-<md 文件名不含扩展名>     例如 economist-2025-01-04-usa
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content" / "magazines"
OUT = ROOT / "scripts" / ".links_kv.json"
OUT_BULK = ROOT / "scripts" / ".links_bulk.json"
FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


def front_matter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    m = FM_RE.match(text)
    if not m:
        return {}
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as exc:
        print(f"  ! front matter 解析失败 {path.name}: {exc}", file=sys.stderr)
        return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bulk", action="store_true", help="同时输出 bulk 上传数组")
    ap.add_argument("--check", action="store_true", help="只校验不写文件")
    args = ap.parse_args()

    records: dict[str, dict[str, str]] = {}
    dupes: list[str] = []
    empty: list[str] = []

    for md in sorted(CONTENT.glob("*/*.md")):
        if md.name == "_index.md":
            continue
        fm = front_matter(md)
        slug = str(fm.get("magazine_slug") or md.parent.name).strip()
        key = f"{slug}-{md.stem}"
        if key in records:
            dupes.append(key)
            continue
        url = str(fm.get("download_url") or "").strip()
        if not url:
            empty.append(key)
            continue
        records[key] = {"url": url, "pwd": str(fm.get("download_pwd") or "").strip()}

    hosts: dict[str, int] = {}
    for rec in records.values():
        m = re.match(r"https?://([^/]+)/", rec["url"])
        host = m.group(1) if m else "?"
        hosts[host] = hosts.get(host, 0) + 1

    print(f"有链接 {len(records)} 期，无链接 {len(empty)} 期，key 冲突 {len(dupes)}")
    print("域名分布:", hosts)
    if dupes:
        print("冲突 key:", dupes[:5])
    if empty:
        print("无链接样例:", empty[:5])

    if args.check:
        return 1 if dupes else 0

    payload = dict(sorted(records.items()))
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"已写出 {OUT.relative_to(ROOT)}（{OUT.stat().st_size / 1024:.0f} KB）")

    if args.bulk:
        bulk = [{"key": k, "value": json.dumps(v, ensure_ascii=False)} for k, v in payload.items()]
        OUT_BULK.write_text(json.dumps(bulk, ensure_ascii=False), encoding="utf-8")
        print(f"已写出 {OUT_BULK.relative_to(ROOT)}（{OUT_BULK.stat().st_size / 1024:.0f} KB）")

    return 1 if dupes else 0


if __name__ == "__main__":
    raise SystemExit(main())
