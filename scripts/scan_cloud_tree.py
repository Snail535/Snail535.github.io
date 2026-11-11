# -*- coding: utf-8 -*-
"""遍历夸克「外文期刊」目录，输出完整文件清单快照 .cloud_tree.json。"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repair_shares as rs  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / ".cloud_tree.json"
ROOT = "外文期刊"


def main() -> None:
    q = rs.Quark()
    rows: list[dict] = []
    dirs = 0

    def rec(fid: str, path: str, depth: int) -> None:
        nonlocal dirs
        try:
            items = q.ls(fid)
        except Exception as exc:  # noqa: BLE001
            print(f"  [跳过] {path}: {exc}", flush=True)
            return
        for x in items:
            name = x["file_name"]
            if x["file_type"] == 0:
                dirs += 1
                if depth < 2:
                    print(f"{'  '*depth}[{path}/{name}]", flush=True)
                rec(x["fid"], f"{path}/{name}", depth + 1)
                time.sleep(0.15)
            else:
                rows.append({
                    "fid": x["fid"],
                    "name": name,
                    "dir": path,
                    "size": x.get("size"),
                    "updated": x.get("updated_at"),
                })

    rec(q.walk(ROOT), ROOT, 0)
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"\n目录数 {dirs}，文件数 {len(rows)} → {OUT}")


if __name__ == "__main__":
    main()
