# -*- coding: utf-8 -*-
"""2026-11-19 批次：为 4 种新刊（CAF/CPE/CPT/CRP，共 55 期）建夸克分享。

映射由 Temp/mag_update/map_batch4.py 推导并校验，规则见该脚本。
复用 build_shares_batch3.py 的建分享与写回实现。

用法：
    python scripts/build_shares_batch4.py --map-only     # 只校验映射
    python scripts/build_shares_batch4.py                # 建分享 -> .new_shares_batch4.json
    python scripts/build_shares_batch4.py --apply-only   # 用上次结果写回 md / .links_kv.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TEMP = ROOT / "Temp" / "mag_update"
OUT = HERE / ".new_shares_batch4.json"

sys.path.insert(0, str(TEMP))
sys.path.insert(0, str(HERE))


def load_map() -> dict[str, tuple[str, str]]:
    from map_batch4 import build_map
    mapping, problems = build_map()
    if problems:
        raise SystemExit(f"映射有问题 {len(problems)} 条，先修：{problems[:5]}")
    return mapping


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
        import build_shares_batch3 as b3
        b3.write_back(json.loads(OUT.read_text(encoding="utf-8"))["done"])
        return

    mp = load_map()
    print(f"待处理 {len(mp)} 期")

    import build_shares_batch3 as b3
    missing = b3.check_tree(mp)
    for m in missing:
        print(f"  [缺] {m}")
    if missing:
        raise SystemExit(f"云盘缺 {len(missing)} 个文件，先不建分享")
    print(f"云盘校验通过：{len(mp)}/{len(mp)}")
    if args.map_only:
        for k, (d, n) in mp.items():
            print(f"  {k:<40} {d}/{n}")
        return

    import repair_shares as rs
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
        print(f"  OK {it['key']:<40} {it['url']}", flush=True)
        time.sleep(0.3)

    OUT.write_text(json.dumps({"done": ok, "failed": failed}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n成功 {len(ok)}，失败 {len(failed)} -> {OUT}")

    if args.apply and ok:
        import build_shares_batch3 as b3
        b3.write_back(ok)


if __name__ == "__main__":
    main()
