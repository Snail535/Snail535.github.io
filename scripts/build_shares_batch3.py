# -*- coding: utf-8 -*-
"""2026-11-16 批次：为 4 种新刊（BBW/FTN/NS/SCA，共 90 期）建夸克分享。

映射规则（由 md key 自动推导，先与 .cloud_tree.json 校验再建）：
    bloomberg-businessweek  2025-01        -> 月刊/BBW/2025/BBW2501.jpg
    fortune                2026-05        -> 月刊/FTN/2026/FTN2604.jpg   （md 月份 = 封面月+1）
    new-scientist          2026-03-21     -> 周刊/NS/2026/03月/NS260321.jpg
    new-scientist          2025-03        -> 周刊/NS/2025/03月/NS250301.jpg （无日即 01 号）
    scientific-american    2026-11         -> 月刊/SCA/2026/SCA2611.jpg

用法：
    python scripts/build_shares_batch3.py            # 建分享并校验 -> .new_shares_batch3.json
    python scripts/build_shares_batch3.py --apply     # 另外写回 md / .links_kv.json / .links_bulk.json
    python scripts/build_shares_batch3.py --apply-only  # 用上次结果直接写回
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CONTENT = ROOT / "content" / "magazines"
LINKS = HERE / ".links_kv.json"
TREE = HERE / ".cloud_tree.json"
OUT = HERE / ".new_shares_batch3.json"

def safe_write(path: Path, text: str) -> None:
    try:
        path.write_text(text, encoding="utf-8", newline="")
    except PermissionError:
        tmp = path.with_name(path.name + f".tmp{os.getpid()}")
        tmp.write_text(text, encoding="utf-8", newline="")
        os.replace(tmp, path)


sys.path.insert(0, str(HERE))
# repair_shares 依赖 requests，只在真正建分享时导入（--apply-only 用不到）


def month_key_to_parts(key: str) -> tuple[int, int, int]:
    m = re.match(r"^(\d{4})-(\d{2})(?:-(\d{2}))?$", key)
    if not m:
        raise ValueError(f"无法解析 key: {key}")
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3) or 1)
    return y, mo, d


def build_map() -> dict[str, tuple[str, str]]:
    """返回 {完整key: (云盘目录, 云盘文件名)}"""
    out: dict[str, tuple[str, str]] = {}

    for md in sorted(CONTENT.glob("bloomberg-businessweek/*.md")):
        if md.name == "_index.md" or "has_download: true" in md.read_text(encoding="utf-8"):
            continue
        key = md.stem
        y, mo, _ = month_key_to_parts(key)
        out[f"bloomberg-businessweek-{key}"] = (
            f"外文期刊/月刊/BBW/{y}", f"BBW{str(y)[2:]}{mo:02d}.jpg")

    for md in sorted(CONTENT.glob("fortune/*.md")):
        if md.name == "_index.md" or "has_download: true" in md.read_text(encoding="utf-8"):
            continue
        key = md.stem
        y, mo, _ = month_key_to_parts(key)
        prev = mo - 1 or 12          # md 月份比云盘封面月晚 1 个月
        py = y if mo > 1 else y - 1
        out[f"fortune-{key}"] = (
            f"外文期刊/月刊/FTN/{py}", f"FTN{str(py)[2:]}{prev:02d}.jpg")

    for md in sorted(CONTENT.glob("new-scientist/*.md")):
        if md.name == "_index.md" or "has_download: true" in md.read_text(encoding="utf-8"):
            continue
        key = md.stem
        y, mo, d = month_key_to_parts(key)
        out[f"new-scientist-{key}"] = (
            f"外文期刊/周刊/NS/{y}/{mo:02d}月", f"NS{str(y)[2:]}{mo:02d}{d:02d}.jpg")

    for md in sorted(CONTENT.glob("scientific-american/*.md")):
        if md.name == "_index.md" or "has_download: true" in md.read_text(encoding="utf-8"):
            continue
        key = md.stem
        y, mo, _ = month_key_to_parts(key)
        out[f"scientific-american-{key}"] = (
            f"外文期刊/月刊/SCA/{y}", f"SCA{str(y)[2:]}{mo:02d}.jpg")

    return out


def check_tree(mp: dict[str, tuple[str, str]]) -> list[str]:
    tree = json.loads(TREE.read_text(encoding="utf-8"))
    have = {(r["dir"], r["name"]) for r in tree}
    missing = []
    for k, (d, n) in mp.items():
        if (d, n) not in have:
            missing.append(f"{k} -> {d}/{n}")
    return missing


def key_split(k: str) -> tuple[str, str]:
    for slug in sorted({p.name for p in CONTENT.iterdir() if p.is_dir()},
                        key=len, reverse=True):
        if k.startswith(slug + "-"):
            return slug, k[len(slug) + 1:]
    raise ValueError(k)


def mark_md(slug: str, key: str, cloud_name: str) -> bool:
    md = CONTENT / slug / f"{key}.md"
    text = md.read_text(encoding="utf-8")
    if "has_download: true" in text:
        return False
    if re.search(r"^download_url:", text, re.M):
        text = re.sub(r"^download_url:.*$", "has_download: true", text, count=1, flags=re.M)
    else:
        text = re.sub(r"^(download_pwd:.*)$", r"\1\nhas_download: true",
                      text, count=1, flags=re.M)
    if "netdisk_file:" not in text:
        text = re.sub(r"^(download_pwd:.*)$",
                      lambda m: f'{m.group(1)}\nnetdisk_file: "{cloud_name}"',
                      text, count=1, flags=re.M)
    safe_write(md, text)
    return True


def write_back(ok: list[dict]) -> int:
    n_md = 0
    for it in ok:
        slug, key = key_split(it["key"])
        n_md += 1 if mark_md(slug, key, it["cloud"].rsplit("/", 1)[1]) else 0
    links = json.loads(LINKS.read_text(encoding="utf-8"))
    for it in ok:
        links[it["key"]] = {"url": it["url"], "pwd": ""}
    safe_write(LINKS, json.dumps(links, ensure_ascii=False, indent=1))
    bulk = [{"key": "i:" + k, "value": json.dumps(v, ensure_ascii=False)}
            for k, v in links.items()]
    safe_write(HERE / ".links_bulk.json", json.dumps(bulk, ensure_ascii=False, indent=0))
    print(f"[apply] 写回 md {n_md} 条、.links_kv.json（含 bulk）共 {len(links)} 条")
    return n_md


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--apply-only", action="store_true")
    ap.add_argument("--delay", type=float, default=1.6)
    ap.add_argument("--map-only", action="store_true", help="只打印映射并校验云盘")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    if args.apply_only:
        data = json.loads(OUT.read_text(encoding="utf-8"))
        write_back(data["done"])
        return

    mp = build_map()
    print(f"待处理 {len(mp)} 期")
    missing = check_tree(mp)
    for m in missing:
        print(f"  [缺] {m}")
    if missing:
        sys.exit(f"云盘缺 {len(missing)} 个文件，先不建分享")
    print(f"云盘校验通过：{len(mp)}/{len(mp)}")
    if args.map_only:
        for k, (d, n) in mp.items():
            print(f"  {k:<36} {d}/{n}")
        return

    import repair_shares as rs  # 延迟导入：仅建分享时需要 requests

    q = rs.Quark()
    done, failed = [], []
    for i, (k, (cdir, cname)) in enumerate(mp.items(), 1):
        try:
            fid = q.find_file(cdir, cname)
            sid = q.share_file(fid, cname)
            print(f"  {i}/{len(mp)} 建分享 {k} -> {sid}", flush=True)
            done.append({"key": k, "share_id": sid, "cloud": f"{cdir}/{cname}"})
        except Exception as exc:  # noqa: BLE001
            failed.append({"key": k, "error": str(exc)})
            print(f"  {i}/{len(mp)} FAIL {k} {exc}", flush=True)
        time.sleep(args.delay)

    print("\n校验…")
    idx = q.share_index()
    ok = []
    for it in done:
        rec = idx.get(it["share_id"])
        if not rec:
            failed.append({"key": it["key"], "error": "列表里找不到分享"})
            continue
        try:
            n = q.share_file_count(rec["pwd_id"])
        except Exception as exc:  # noqa: BLE001
            failed.append({"key": it["key"], "error": f"校验失败 {exc}"})
            continue
        if n != 1:
            failed.append({"key": it["key"], "error": f"文件数 {n}（应为 1）"})
            continue
        it["url"] = f"https://pan.quark.cn/s/{rec['pwd_id']}"
        ok.append(it)
        print(f"  OK {it['key']:<36} {it['url']}", flush=True)
        time.sleep(0.3)

    safe_write(OUT, json.dumps({"done": ok, "failed": failed}, ensure_ascii=False, indent=1))
    print(f"\n成功 {len(ok)}，失败 {len(failed)} -> {OUT}")

    if args.apply and ok:
        write_back(ok)


if __name__ == "__main__":
    main()
