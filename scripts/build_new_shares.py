# -*- coding: utf-8 -*-
"""2026-11-15 批次：为 33 期（32 新增 + kandy 遗留）按精确映射建夸克分享。

用法：
    python scripts/build_new_shares.py           # 建分享并校验 -> .new_shares33.json
    python scripts/build_new_shares.py --apply    # 另外写回 .links_kv.json / md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CONTENT = ROOT / "content" / "magazines"
LINKS = HERE / ".links_kv.json"
OUT = HERE / ".new_shares33.json"

sys.path.insert(0, str(HERE))
import repair_shares as rs  # noqa: E402

# 页面 key -> (云盘目录, 云盘文件名)
MAP: dict[str, tuple[str, str]] = {
    "economist-2025-03-29-usa": ("外文期刊/周刊/ECO/2025/03月", "ECOUS250329.jpg"),
    "economist-2026-06-06-usa": ("外文期刊/周刊/ECO/2026/06月", "ECOUS260606.jpg"),
    "economist-2026-09-19-usa": ("外文期刊/周刊/ECO/2026/09月", "ECOUS260919.jpg"),
    "economist-2026-09-26-usa": ("外文期刊/周刊/ECO/2026/09月", "ECOUS260926.jpg"),
    "economist-2026-10-24-usa": ("外文期刊/周刊/ECO/2026/10月", "ECOUS261024.jpg"),
    "economist-2026-10-31-usa": ("外文期刊/周刊/ECO/2026/10月", "ECOUS261031.jpg"),
    "economist-2026-11-07-usa": ("外文期刊/周刊/ECO/2026/11月", "ECOUS261107.jpg"),
    "science-2026-01-22": ("外文期刊/周刊/SCI/2026/01月", "SCIUS260122.jpg"),
    "science-2026-01-29": ("外文期刊/周刊/SCI/2026/01月", "SCIUS260129.jpg"),
    "science-2026-02-05": ("外文期刊/周刊/SCI/2026/02月", "SCIUS260205.jpg"),
    "science-2026-02-12": ("外文期刊/周刊/SCI/2026/02月", "SCIUS260212.jpg"),
    "science-2026-10-22": ("外文期刊/周刊/SCI/2026/10月", "SCIUS261022.jpg"),
    "science-2026-10-29": ("外文期刊/周刊/SCI/2026/10月", "SCIUS261029.jpg"),
    "science-2026-11-05": ("外文期刊/周刊/SCI/2026/11月", "SCIUS261105.jpg"),
    "guardian-weekly-2025-02-07": ("外文期刊/周刊/GUW/2025/02月", "GUWUK250207.jpg"),
    "guardian-weekly-2025-10-24": ("外文期刊/周刊/GUW/2025/10月", "GUWUK251024.jpg"),
    "guardian-weekly-2026-10-23": ("外文期刊/周刊/GUW/2026/10月", "GUWUK261023.jpg"),
    "guardian-weekly-2026-10-30": ("外文期刊/周刊/GUW/2026/10月", "GUWUK261030.jpg"),
    "guardian-weekly-2026-11-06": ("外文期刊/周刊/GUW/2026/11月", "GUWUK261106.jpg"),
    "new-yorker-2026-01-12": ("外文期刊/周刊/NYK/2026/01月", "NYK260112.jpg"),
    "new-yorker-2026-01-19": ("外文期刊/周刊/NYK/2026/01月", "NYK260119.jpg"),
    "new-yorker-2026-10-26": ("外文期刊/周刊/NYK/2026/10月", "NYK261026.jpg"),
    "new-yorker-2026-11-02": ("外文期刊/周刊/NYK/2026/11月", "NYK261102.jpg"),
    "new-yorker-2026-11-09": ("外文期刊/周刊/NYK/2026/11月", "NYK261109.jpg"),
    "time-2026-11-09-usa": ("外文期刊/月刊/TIM/2026/11月", "TIMUS261109.jpg"),
    "forbes-2026-11-usa": ("外文期刊/月刊/FOR/2026/USA", "FORUS2610.jpg"),
    "fhm-2025-04-france": ("外文期刊/月刊/FHM/2025/France", "FHMFR2504.jpg"),
    "fhm-2026-11-mexico": ("外文期刊/月刊/FHM/2026/Mexico", "FHMMX2611.jpg"),
    "fhm-2026-11-sweden": ("外文期刊/月刊/FHM/2026/Sweden", "FHMSE2611.jpg"),
    "fhm-2026-11-usa-us": ("外文期刊/月刊/FHM/2026/USA", "FHMUS2611.jpg"),
    "readers-digest-2026-11-india": ("外文期刊/月刊/RDG/2026/India", "RDGIN2611.jpg"),
    "the-atlantic-2026-12": ("外文期刊/月刊/ATL/2026", "ATLUS2612.jpg"),
    "kandy-2024-12": ("外文期刊/月刊/KDY/2024", "KDYHD2412.jpg"),
}


def key_split(k: str) -> tuple[str, str]:
    """'economist-2025-03-29-usa' -> ('economist', '2025-03-29-usa')"""
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
    md.write_text(text, encoding="utf-8", newline="")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--apply-only", action="store_true",
                    help="跳过建分享，直接用 .new_shares33.json 的结果写回")
    ap.add_argument("--delay", type=float, default=1.6)
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    if args.apply_only:
        data = json.loads(OUT.read_text(encoding="utf-8"))
        ok = data["done"]
        n_md = 0
        for it in ok:
            slug, key = key_split(it["key"])
            n_md += 1 if mark_md(slug, key, it["cloud"].rsplit("/", 1)[1]) else 0
        links = json.loads(LINKS.read_text(encoding="utf-8"))
        for it in ok:
            links[it["key"]] = {"url": it["url"], "pwd": ""}
        LINKS.write_text(json.dumps(links, ensure_ascii=False, indent=1), encoding="utf-8")
        bulk = [{"key": "i:" + k, "value": json.dumps(v, ensure_ascii=False)}
                for k, v in links.items()]
        (HERE / ".links_bulk.json").write_text(json.dumps(bulk, ensure_ascii=False, indent=0),
                                               encoding="utf-8")
        print(f"[apply-only] 写回 md {n_md} 条、.links_kv.json（含 bulk）共 {len(links)} 条")
        return

    q = rs.Quark()
    done, failed = [], []
    for i, (k, (cdir, cname)) in enumerate(MAP.items(), 1):
        try:
            fid = q.find_file(cdir, cname)
            sid = q.share_file(fid, cname)
            print(f"  {i}/{len(MAP)} 建分享 {k} -> {sid}", flush=True)
            done.append({"key": k, "share_id": sid, "cloud": f"{cdir}/{cname}"})
        except Exception as exc:  # noqa: BLE001
            failed.append({"key": k, "error": str(exc)})
            print(f"  {i}/{len(MAP)} FAIL {k} {exc}", flush=True)
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
        print(f"  OK {it['key']:<32} {it['url']}", flush=True)
        time.sleep(0.3)

    OUT.write_text(json.dumps({"done": ok, "failed": failed}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n成功 {len(ok)}，失败 {len(failed)} -> {OUT}")

    if args.apply and ok:
        n_md = 0
        for it in ok:
            slug, key = key_split(it["key"])
            n_md += 1 if mark_md(slug, key, it["cloud"].rsplit("/", 1)[1]) else 0
        links = json.loads(LINKS.read_text(encoding="utf-8"))
        for it in ok:
            links[it["key"]] = {"url": it["url"], "pwd": ""}
        LINKS.write_text(json.dumps(links, ensure_ascii=False, indent=1), encoding="utf-8")
        bulk = [{"key": "i:" + k, "value": json.dumps(v, ensure_ascii=False)}
                for k, v in links.items()]
        (HERE / ".links_bulk.json").write_text(json.dumps(bulk, ensure_ascii=False, indent=0),
                                               encoding="utf-8")
        print(f"已写回 md {n_md} 条、.links_kv.json（含 bulk）共 {len(links)} 条")


if __name__ == "__main__":
    main()
