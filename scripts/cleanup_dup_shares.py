# -*- coding: utf-8 -*-
"""清理 2026-11-15 批次中重复创建的第一批分享（--apply 失误导致每文件建了两次）。

保留 .new_shares33.json（第二批，已写回 KV）里的 share_id，
删除同名 title、今天创建、且不在保留名单里的分享。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import repair_shares as rs  # noqa: E402

OUT = HERE / ".new_shares33.json"

TITLES = {
    "ECOUS250329.jpg", "ECOUS260606.jpg", "ECOUS260919.jpg", "ECOUS260926.jpg",
    "ECOUS261024.jpg", "ECOUS261031.jpg", "ECOUS261107.jpg",
    "SCIUS260122.jpg", "SCIUS260129.jpg", "SCIUS260205.jpg", "SCIUS260212.jpg",
    "SCIUS261022.jpg", "SCIUS261029.jpg", "SCIUS261105.jpg",
    "GUWUK250207.jpg", "GUWUK251024.jpg", "GUWUK261023.jpg", "GUWUK261030.jpg",
    "GUWUK261106.jpg",
    "NYK260112.jpg", "NYK260119.jpg", "NYK261026.jpg", "NYK261102.jpg", "NYK261109.jpg",
    "TIMUS261109.jpg", "FORUS2610.jpg", "FHMFR2504.jpg", "FHMMX2611.jpg",
    "FHMSE2611.jpg", "FHMUS2611.jpg", "RDGIN2611.jpg", "ATLUS2612.jpg",
    "KDYHD2412.jpg",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--go", action="store_true", help="真正执行删除（默认只预览）")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    keep = {it["share_id"] for it in json.loads(OUT.read_text(encoding="utf-8"))["done"]}
    q = rs.Quark()
    idx = q.share_index()

    # 打印一条记录的时间字段，确认命名
    sample = next(iter(idx.values()))
    keys = [k for k in sample if "time" in k.lower() or "creat" in k.lower()]
    print("时间字段候选:", keys, "->", {k: sample.get(k) for k in keys})

    victims = []
    for sid, rec in idx.items():
        if sid in keep:
            continue
        title = rec.get("title", "")
        if title not in TITLES:
            continue
        ts = rec.get("created_at") or 0
        try:
            day = datetime.fromtimestamp(int(ts) / 1000).strftime("%Y-%m-%d")
        except (TypeError, ValueError):
            day = "?"
        if day == "2026-11-15":
            victims.append((sid, title, day))

    print(f"\n保留（第二批已写回 KV）{len(keep)} 条；待删除 {len(victims)} 条：")
    for sid, title, created in victims:
        print(f"  {sid}  {title}  {created}")

    if args.go and victims:
        ids = [v[0] for v in victims]
        j = q._post("share/delete", {"share_ids": ids})
        print("\n删除结果:", json.dumps(j, ensure_ascii=False)[:200])
        # 复核
        idx2 = q.share_index()
        left = [v for v in victims if v[0] in idx2]
        print(f"复核残留 {len(left)} 条")


if __name__ == "__main__":
    main()
