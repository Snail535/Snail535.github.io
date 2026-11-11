# -*- coding: utf-8 -*-
"""校验刚重建的分享，并把结果写回 KV 数据文件。

用法：
    python scripts/verify_repair.py            # 校验 + 写回 .links_kv.json / .links_bulk.json / .links_patch.json
    python scripts/verify_repair.py --dry-run  # 只校验
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

import repair_shares as rs

HERE = Path(__file__).resolve().parent
LINKS = HERE / ".links_kv.json"
CHECK = HERE / ".share_check.json"
SHARES_SNAP = HERE / ".cloud_shares.json"
SINCE = 1794407347908  # 本轮重建开始的时间戳（毫秒，21:43 左右），用于挑出新分享


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    bad_keys = [x["key"] for x in json.loads(CHECK.read_text(encoding="utf-8"))["bad"]]
    links = json.loads(LINKS.read_text(encoding="utf-8"))
    snap = json.loads(SHARES_SNAP.read_text(encoding="utf-8"))
    by_pwd = {s["pwd_id"]: s for s in snap}

    # key -> 云端文件名
    p2 = HERE / ".cloud_shares2.json"
    extra = {}
    if p2.exists():
        for k, v in json.loads(p2.read_text(encoding="utf-8")).items():
            if isinstance(v, dict) and v.get("name"):
                extra[k] = v["name"]
    name_of = {}
    for k in bad_keys:
        rec = by_pwd.get(links[k]["url"].split("/")[-1])
        if rec:
            name_of[k] = rec["title"]
        elif k in extra:
            name_of[k] = extra[k]

    q = rs.Quark()
    idx = q.share_index()
    by_title: dict[str, list[dict]] = collections.defaultdict(list)
    for r in idx.values():
        by_title[r.get("title", "")].append(r)

    done, failed = [], []
    for k in bad_keys:
        name = name_of.get(k)
        if not name:
            failed.append({"key": k, "error": "没有文件名映射"})
            continue
        cands = [r for r in by_title.get(name, []) if (r.get("created_at") or 0) >= SINCE]
        if not cands:
            failed.append({"key": k, "error": "找不到本轮新建的分享", "name": name})
            continue
        rec = max(cands, key=lambda r: r.get("created_at") or 0)
        try:
            n = q.share_file_count(rec["pwd_id"])
        except Exception as exc:  # noqa: BLE001
            failed.append({"key": k, "error": f"校验失败 {exc}", "name": name})
            continue
        if n <= 0:
            failed.append({"key": k, "error": "文件数=0", "name": name})
            continue
        done.append(
            {
                "key": k,
                "name": name,
                "share_id": rec["share_id"],
                "new_url": f"https://pan.quark.cn/s/{rec['pwd_id']}",
                "new_pwd": "",
            }
        )
        print(f"  OK  {k:30s} {done[-1]['new_url']}  文件数={n}", flush=True)

    print(f"\n校验结果：正常 {len(done)}，异常 {len(failed)}")
    for f in failed[:10]:
        print("  ", f)

    if args.dry_run or not done:
        return

    for t in done:
        links[t["key"]] = {"url": t["new_url"], "pwd": t["new_pwd"]}
    LINKS.write_text(json.dumps(links, ensure_ascii=False, indent=1), encoding="utf-8")

    bulk = [
        {"key": "i:" + k, "value": json.dumps(v, ensure_ascii=False)}
        for k, v in links.items()
    ]
    (HERE / ".links_bulk.json").write_text(json.dumps(bulk, ensure_ascii=False), encoding="utf-8")

    patch = [
        {"key": "i:" + t["key"], "value": json.dumps({"url": t["new_url"], "pwd": t["new_pwd"]}, ensure_ascii=False)}
        for t in done
    ]
    (HERE / ".links_patch.json").write_text(json.dumps(patch, ensure_ascii=False), encoding="utf-8")
    (HERE / ".repair_result.json").write_text(
        json.dumps({"done": done, "failed": failed}, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"已写回本地数据，增量补丁 {len(patch)} 条 -> .links_patch.json")


if __name__ == "__main__":
    main()
