# -*- coding: utf-8 -*-
"""2026-11-20 批次 5：为 130 个新期次建夸克分享。

映射来源（两路合并）：
  1) data/issue_overrides.yaml 的 cloud 字段 —— 显式指定，覆盖 116 期
  2) 按 slug 规则推导 —— 补齐文件名里没有月份标记、自然解析出来的 14 期

用法：
    python scripts/build_shares_batch5.py --map-only   # 只打印映射并校验云盘
    python scripts/build_shares_batch5.py              # 建分享并校验 -> .new_shares_batch5.json
    python scripts/build_shares_batch5.py --apply      # 另外写回 md / .links_kv.json / .links_bulk.json
    python scripts/build_shares_batch5.py --apply-only # 用上次结果直接写回
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
SRC = Path(r"E:\迅雷下载\英文杂志\原文档")
LINKS = HERE / ".links_kv.json"
TREE = HERE / ".cloud_tree.json"
OVR = ROOT / "data" / "issue_overrides.yaml"
OUT = HERE / ".new_shares_batch5.json"
DUMP = ROOT / ".scan_dump.json"


def safe_write(path: Path, text: str) -> None:
    try:
        path.write_text(text, encoding="utf-8", newline="")
    except PermissionError:
        tmp = path.with_name(path.name + f".tmp{os.getpid()}")
        tmp.write_text(text, encoding="utf-8", newline="")
        os.replace(tmp, path)


# ---------------------------------------------------------------- 云盘命名规则
# slug -> (云盘目录模板, 文件名模板)
#   目录模板用 {y}，文件名模板用 {y}/{mo}
RULES = {
    "china-report":        ("外文期刊/周刊/CRP/{y}",   "CRP{y2}{mo:02d}.jpg"),
    "china-report-asean":  ("外文期刊/月刊/CRA/{y}",   "CRA{y2}{mo:02d}.jpg"),
    "china-today":         ("外文期刊/月刊/CTD/{y}",   "CTD{y2}{mo:02d}.jpg"),
    "i-love-english-junior": ("外文期刊/月刊/ILE/{y}", "ILE{y2}{mo:02d}.jpg"),
    "spielbox":            ("外文期刊/月刊/SPB/{y}",   "SPB{y2}{mo:02d}.jpg"),
    "learn-hot-english":   ("外文期刊/月刊/LHE/{y}",   None),  # 期号制，见下
}


def derive_cloud(slug: str, key: str) -> str | None:
    """按规则推导云盘路径；推不出来返回 None。"""
    m = re.match(r"^(\d{4})-(\d{2})(?:-(\d{2}))?(?:-(.+))?$", key)
    if not m:
        return None
    rule = RULES.get(slug)
    if not rule:
        return None
    y, mo = int(m.group(1)), int(m.group(2))
    d, name_tpl = rule
    d = d.format(y=y)
    if name_tpl is None:
        # LHE 期号制：260 = 2024-01，期号连续递增
        im = re.search(r"issue-(\d+)$", key)
        if not im:
            return None
        name = f"LHE{im.group(1)}.jpg"
    else:
        name = name_tpl.format(y=y, y2=str(y)[2:], mo=mo)
    return f"{d}/{name}"


def build_map() -> tuple[dict[str, tuple[str, str]], list[str]]:
    """返回 ({KV key: (云盘目录, 云盘文件名)}, 说明文字列表)"""
    import yaml
    ov = yaml.safe_load(OVR.read_text(encoding="utf-8")) or {}

    # 覆盖表的键是相对「原文档」的路径；dump 里存的是绝对路径
    dump = json.loads(DUMP.read_text(encoding="utf-8"))
    rel_of = {}
    for r in dump:
        rel = os.path.relpath(r["pdf"], SRC).replace("\\", "/")
        rel_of[rel] = r

    # md key -> (slug, file_name)
    md_by_file = {}
    for slug_dir in sorted(CONTENT.iterdir()):
        if not slug_dir.is_dir():
            continue
        for md in sorted(slug_dir.glob("*.md")):
            if md.name == "_index.md":
                continue
            txt = md.read_text(encoding="utf-8")
            if "has_download: true" in txt:
                continue
            fn = re.search(r'^file_name:\s*"?(.*?)"?\s*$', txt, re.M)
            if not fn:
                continue
            md_by_file.setdefault(fn.group(1), []).append((slug_dir.name, md.stem))

    out: dict[str, tuple[str, str]] = {}
    notes: list[str] = []
    for rel, r in rel_of.items():
        item = ov.get(rel) or {}
        if item.get("skip"):
            continue
        if "has_download: true" in (CONTENT / r["slug"] / f"{r['key']}.md").read_text(encoding="utf-8"):
            continue
        base = os.path.basename(rel)
        if base not in md_by_file:
            continue
        if len(md_by_file[base]) > 1:
            notes.append(f"  [多页同名] {base} -> {md_by_file[base]}")
        slug, key = md_by_file[base][0]

        cloud = item.get("cloud")
        src_kind = "覆盖表"
        if not cloud:
            cloud = derive_cloud(slug, key)
            src_kind = "规则推导"
        if not cloud:
            notes.append(f"  [无法映射] {slug}/{key}  ({rel})")
            continue
        d, n = cloud.rsplit("/", 1)
        out[f"{slug}-{key}"] = (d, n)
    return out, notes


def check_tree(mp: dict[str, tuple[str, str]]) -> list[str]:
    tree = json.loads(TREE.read_text(encoding="utf-8"))
    have = {(r["dir"], r["name"]) for r in tree}
    return [f"{k} -> {d}/{n}" for k, (d, n) in mp.items() if (d, n) not in have]


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
    ap.add_argument("--map-only", action="store_true")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    if args.apply_only:
        data = json.loads(OUT.read_text(encoding="utf-8"))
        write_back(data["done"])
        return

    mp, notes = build_map()
    for n in notes:
        print(n)
    print(f"待处理 {len(mp)} 期")
    missing = check_tree(mp)
    for m in missing:
        print(f"  [缺] {m}")
    if missing:
        sys.exit(f"云盘缺 {len(missing)} 个文件，先不建分享")
    print(f"云盘校验通过：{len(mp)}/{len(mp)}")
    if args.map_only:
        for k, (d, n) in sorted(mp.items()):
            print(f"  {k:<40} {d}/{n}")
        return

    import repair_shares as rs

    q = rs.Quark()
    done, failed = [], []
    for i, (k, (cdir, cname)) in enumerate(sorted(mp.items()), 1):
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
        print(f"  OK {it['key']:<40} {it['url']}", flush=True)
        time.sleep(0.3)

    safe_write(OUT, json.dumps({"done": ok, "failed": failed}, ensure_ascii=False, indent=1))
    print(f"\n成功 {len(ok)}，失败 {len(failed)} -> {OUT}")

    if args.apply and ok:
        write_back(ok)


if __name__ == "__main__":
    main()
