# -*- coding: utf-8 -*-
"""为「缺链接」的期次补分享：按云端现存图种建分享，写 KV + 给 md 打 has_download。

依赖登录态：python scripts/quark_login.py 扫码一次。

用法：
    python scripts/fill_missing.py --dry-run   # 只打印映射关系
    python scripts/fill_missing.py             # 建分享并校验，输出 .fill_result.json
    python scripts/fill_missing.py --apply     # 同时更新链接数据与 md 标记
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repair_shares as rs  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TREE = HERE / ".cloud_tree.json"
LINKS = HERE / ".links_kv.json"
RESULT = HERE / ".fill_result.json"

# 页面 key -> (云端目录, 云端文件名)
MAP: dict[str, tuple[str, str]] = {
    "forbes-2026-01-usa": ("外文期刊/月刊/FOR/2026/USA", "FORUS2512.jpg"),
    "guardian-weekly-2026-05": ("外文期刊/周刊/GUW/2026/05月", "GUWUK260501.jpg"),
    "kandy-2026-01-anniversary": ("外文期刊/月刊/KDY/2026", "KDYAN26.jpg"),
    "new-yorker-2026-07-13": ("外文期刊/周刊/NYK/2026/07月", "NYK260706.jpg"),
    "new-yorker-2026-08-31": ("外文期刊/周刊/NYK/2026/08月", "NYK260824.jpg"),
    "readers-digest-2026-01-australia": ("外文期刊/月刊/RDG/2026/Australia", "RDGAU2512.jpg"),
    "readers-digest-2026-01-usa": ("外文期刊/月刊/RDG/2026/USA", "RDGUS2512.jpg"),
    "readers-digest-2026-03-australia": ("外文期刊/月刊/RDG/2026/Australia", "RDGAU2602.jpg"),
    "readers-digest-2026-07-australia": ("外文期刊/月刊/RDG/2026/Australia", "RDGAU2606.jpg"),
    "readers-digest-2026-09-australia": ("外文期刊/月刊/RDG/2026/Australia", "RDGAU2608.jpg"),
    "science-2026-10": ("外文期刊/周刊/SCI/2026/10月", "SCIUS261001.jpg"),
}

# 复用已有分享：页面 key -> 旧 key（只搬 key，不重建分享）
REUSE: dict[str, str] = {
    # BOUBD2506（主刊 Boudoir 2025-06）的分享原先错挂在子系列页上，正好搬给主刊页
    "boudoir-inspiration-2025-06": "boudoir-inspiration-2025-06-boudoir",
    "kandy-2026-06-midsummers": "kandy-2026-06",
}

# 历史映射有误、需要重建到正确文件的条目：key -> (目录, 文件名)
FIX: dict[str, tuple[str, str]] = {
    # 该页是「Boudoir Issue」子系列，应指向 BOUBI 而非主刊的 BOUBD
    "boudoir-inspiration-2025-06-boudoir": ("外文期刊/月刊/BOU/2025/Boudoir", "BOUBI2506.jpg"),
}


def key_to_md() -> dict[str, Path]:
    """页面 key -> md 路径（slug 含连字符，不能简单 split）。"""
    data = json.loads((HERE / ".missing13.json").read_text(encoding="utf-8"))
    out = {}
    for it in data:
        stem = it["file"].split("/")[-1][:-3]
        out[f"{it['slug']}-{stem}"] = ROOT / it["file"]
    return out


def add_flag(path: Path) -> bool:
    """在 front matter 里补 has_download: true，返回是否改动。"""
    text = path.read_text(encoding="utf-8")
    if re.search(r"^has_download:\s*true\s*$", text, re.M):
        return False
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not m:
        raise RuntimeError(f"{path} 没有 front matter")
    fm = m.group(1)
    anchor = re.search(r"^download_pwd:.*$", fm, re.M)
    if anchor:
        new_fm = fm[: anchor.end()] + "\nhas_download: true" + fm[anchor.end():]
    else:
        new_fm = fm + "\nhas_download: true"
    path.write_text(text[: m.start(1)] + new_fm + text[m.end(1):], encoding="utf-8")
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true", help="写回链接数据 + md 标记")
    ap.add_argument("--delay", type=float, default=1.6)
    args = ap.parse_args()

    tree = {r["name"]: r for r in json.loads(TREE.read_text(encoding="utf-8"))}
    links = json.loads(LINKS.read_text(encoding="utf-8"))

    for label, table in (("新建", MAP), ("修正", FIX)):
        for key, (d, name) in table.items():
            rec = tree.get(name)
            ok = rec and rec["dir"] == d
            print(f"[{label}] {key:44s} {name:18s} "
                  f"{'✓ ' + d if ok else '✗ ' + (rec['dir'] if rec else '文件不存在')}")
    print()
    for key, old in REUSE.items():
        print(f"[复用] {key:44s} ← {old}  {links.get(old, {}).get('url', '无')}")

    if args.dry_run:
        return

    q = rs.Quark()
    done, failed = [], []
    # 复用条目的 URL 先抓下来，避免随后被 FIX 覆盖
    snapshot = {k: (links.get(old) or {}).get("url") for k, old in REUSE.items()}

    # 1) 复用已有分享
    for key, old in REUSE.items():
        url = snapshot.get(key)
        if not url:
            failed.append({"key": key, "error": f"旧 key {old} 无链接"})
            continue
        pid = url.split("/")[-1]
        n = q.share_file_count(pid)
        if n <= 0:
            failed.append({"key": key, "error": "旧分享内文件数为 0"})
            continue
        done.append({"key": key, "name": "", "url": url, "files": n, "reused": old})
        print(f"复用 OK {key:40s} {url} files={n}", flush=True)

    # 2) 新建分享（含修正条目）
    todo = list(MAP.items()) + list(FIX.items())
    for i, (key, (d, name)) in enumerate(todo, 1):
        try:
            fid = q.find_file(d, name)
            sid = q.share_file(fid, name)
            time.sleep(0.8)
            n = None
            for _ in range(3):
                idx = q.share_index()
                rec = idx.get(sid)
                if rec:
                    n = q.share_file_count(rec["pwd_id"])
                    break
                time.sleep(1.2)
            if not n:
                raise RuntimeError("分享列表里查不到刚建的分享")
            done.append({"key": key, "name": name, "url": f"https://pan.quark.cn/s/{rec['pwd_id']}",
                         "files": n, "reused": None})
            print(f"  {i}/{len(todo)} OK   {key:40s} {done[-1]['url']} files={n}", flush=True)
        except Exception as exc:  # noqa: BLE001
            failed.append({"key": key, "error": str(exc)})
            print(f"  {i}/{len(todo)} FAIL {key:40s} {exc}", flush=True)
        time.sleep(args.delay)

    RESULT.write_text(json.dumps({"done": done, "failed": failed}, ensure_ascii=False, indent=1),
                      encoding="utf-8")
    print(f"\n成功 {len(done)}，失败 {len(failed)}")

    if args.apply and done:
        for t in done:
            links[t["key"]] = {"url": t["url"], "pwd": ""}
        LINKS.write_text(json.dumps(dict(sorted(links.items())), ensure_ascii=False, indent=1),
                         encoding="utf-8")
        patch = [{"key": "i:" + t["key"], "value": json.dumps({"url": t["url"], "pwd": ""},
                                                             ensure_ascii=False)} for t in done]
        (HERE / ".fill_patch.json").write_text(json.dumps(patch, ensure_ascii=False, indent=0),
                                               encoding="utf-8")
        changed = []
        paths = key_to_md()
        for t in done:
            p = paths.get(t["key"])
            if p and p.exists() and add_flag(p):
                changed.append(str(p.relative_to(ROOT)))
        print(f"已写 .links_kv.json，补丁 {len(patch)} 条；md 改动 {len(changed)} 个")
        for c in changed:
            print("  ", c)


if __name__ == "__main__":
    main()
