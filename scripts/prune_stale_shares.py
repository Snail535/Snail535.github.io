# -*- coding: utf-8 -*-
"""清理失效（空壳）的夸克分享：只删「标题在待修清单里 + 分享内文件数为 0」的记录。

用法：
    python scripts/prune_stale_shares.py --dry-run
    python scripts/prune_stale_shares.py --apply
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

import repair_shares as rs

HERE = Path(__file__).resolve().parent
CHECK = HERE / ".share_check.json"
SHARES_SNAP = HERE / ".cloud_shares.json"
RESULT = HERE / ".repair_result.json"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    done = json.loads(RESULT.read_text(encoding="utf-8"))["done"]
    keep_ids = {d["share_id"] for d in done}

    # 待修清单里的文件名（直接用本轮新建结果，避免依赖 check_shares 的输出文件）
    titles = {d["name"] for d in done}
    print(f"涉及文件名 {len(titles)} 个，新分享 {len(keep_ids)} 条（这些绝不删）")

    q = rs.Quark()
    idx = q.share_index()
    cand_by_title: dict[str, list[dict]] = collections.defaultdict(list)
    for r in idx.values():
        if r.get("title") in titles and r.get("share_id") not in keep_ids:
            cand_by_title[r["title"]].append(r)

    stale, alive = [], []
    for title, recs in cand_by_title.items():
        for r in recs:
            try:
                n = q.share_file_count(r["pwd_id"])
            except Exception as exc:  # noqa: BLE001
                print(f"  跳过 {title} {r['pwd_id']}（校验异常：{exc}）")
                continue
            if n == 0:
                stale.append(r)
                print(f"  空壳 {title:20s} {r['pwd_id']}  {r.get('created_at')}")
            else:
                alive.append(r)
                print(f"  保留 {title:20s} {r['pwd_id']}  文件数={n}")

    print(f"\n空壳 {len(stale)} 条，仍在用 {len(alive)} 条")
    if not args.apply or not stale:
        return

    ids = [r["share_id"] for r in stale]
    for i in range(0, len(ids), 20):
        chunk = ids[i : i + 20]
        r = q.s.post(rs.API + "/share/delete", params=rs.Q, json={"share_ids": chunk}, timeout=30)
        j = r.json()
        print(f"  删除 {len(chunk)} 条 -> code={j.get('code')} {j.get('message')}")

    print("\n复查：")
    idx2 = q.share_index()
    left = [r for r in idx2.values() if r.get("title") in titles and r.get("share_id") not in keep_ids]
    print(f"  同标题且非新分享的记录还剩 {len(left)} 条")


if __name__ == "__main__":
    main()
