# -*- coding: utf-8 -*-
"""为本次新增刊物批量创建夸克分享。

流程：从 .cloud_tree.json 取 `外文期刊/月刊/<CODE>/` 下的图种文件名，
按各刊命名规律映射到 content/magazines/<slug>/<key>.md，再逐条建分享。

用法：
    python scripts/new_links.py --dry-run     # 只打印匹配表
    python scripts/new_links.py               # 建分享并校验，写 .new_shares.json
    python scripts/new_links.py --apply       # 另外写回 .links_kv.json / .links_bulk.json
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
TREE = HERE / ".cloud_tree.json"
LINKS = HERE / ".links_kv.json"
OUT = HERE / ".new_shares.json"

sys.path.insert(0, str(HERE))
import repair_shares as rs  # noqa: E402

# 本站 slug -> 云盘目录代码（画册类，文件在 月刊/<CODE>/）
NEW_MAGS = {
    "bossing": "BOS",
    "exotic": "EXO",
    "inciter": "INC",
    "inside-out-babes": "IOB",
    "kandy": "KDY",
    "lingerie-plus": "LGP",
    "maxim": "MAX",
    "mancave-playbabes": "MPB",
    "playbabes": "PBS",
    "rhk": "RHK",
    "ric": "RIC",
}

# 老档（2019-2024）在云盘是按刊分目录存的 PDF 原文件，文件名 = 本地 PDF 名 + ".sssEFs"
OLD_SUFFIX = ".sssEFs"

# PBS 特刊后缀 -> md 的 key 修饰
PBS_SUF = {
    "ES": "early",   # Early Spring
    "SP": None,      # Spring
    "SU": None,      # Summer
    "FA": None,      # Fall
    "WI": None,      # Winter
    "SW": "swimsuit",
}


def load_md(slug: str) -> list[dict]:
    out = []
    for md in sorted(CONTENT.glob(f"{slug}/*.md")):
        if md.name == "_index.md":
            continue
        text = md.read_text(encoding="utf-8")

        def grab(name):
            m = re.search(rf'^{name}:\s*"?(.*?)"?\s*$', text, re.M)
            return m.group(1) if m else ""

        label = grab("issue_label")
        # 起始年月：label 形如 "2025 年 1 月 – 2025 年 2 月 · IOB"
        ym = re.findall(r"(\d{4}) 年 (\d{1,2}) 月", label)
        start = (int(ym[0][0]), int(ym[0][1])) if ym else None
        end = (int(ym[-1][0]), int(ym[-1][1])) if ym else None
        fname = grab("file_name")
        # IOB 三个版本：Extreme / Special / 普通，按源文件名判定，云盘后缀一一对应
        if "Extreme" in fname:
            kind = "E"
        elif "Special" in fname:
            kind = "S"
        else:
            kind = ""
        out.append({"slug": slug, "key": md.stem, "label": label,
                    "issue": grab("issue"), "file": fname, "kind": kind,
                    "start": start, "end": end,
                    "has_dl": "has_download: true" in text})
    return out


def cloud_files() -> dict[str, list[dict]]:
    rows = json.loads(TREE.read_text(encoding="utf-8"))
    by_code: dict[str, list[dict]] = {}
    for r in rows:
        m = re.search(r"/月刊/([A-Za-z]+)/", r["dir"])
        if not m or not r["name"].lower().endswith(".jpg"):
            continue
        by_code.setdefault(m.group(1).upper(), []).append(r)
    return by_code


def parse_name(name: str, code: str):
    """CODE[SUF]YYMM.jpg -> (suf, (yy, mm))"""
    stem = name.rsplit(".", 1)[0]
    if not stem.upper().startswith(code):
        return None
    rest = stem[len(code):]
    m = re.fullmatch(r"([A-Z]{0,2})(\d{2})(\d{2})", rest.upper())
    if not m:
        return None
    suf, yy, mm = m.group(1), int(m.group(2)), int(m.group(3))
    if not 1 <= mm <= 12:
        return None
    return suf, (2000 + yy, mm)


def match_all() -> list[dict]:
    rows = json.loads(TREE.read_text(encoding="utf-8"))
    by_name: dict[str, list[dict]] = {}
    for r in rows:
        by_name.setdefault(r["name"], []).append(r)

    files = cloud_files()
    pairs, problems = [], []

    for slug, code in NEW_MAGS.items():
        items = [x for x in load_md(slug) if not x["has_dl"]]
        pool = []
        for f in files.get(code, []):
            pn = parse_name(f["name"], code)
            if pn:
                pool.append({"name": f["name"], "dir": f["dir"], "suf": pn[0], "ym": pn[1]})
        used = set()

        for it in items:
            # 1) 老档（2019-2024）：云盘存的是 PDF 原文件，名字只多了 .sssEFs
            hit = by_name.get(it["file"] + OLD_SUFFIX) or by_name.get(it["file"])
            if hit and hit[0]["name"] not in used:
                pick = hit[0]
                used.add(pick["name"])
                it.update({"cloud_name": pick["name"], "cloud_dir": pick["dir"]})
                pairs.append(it)
                continue

            if not it["start"]:
                problems.append((it, "无法解析期次"))
                continue
            cand = []
            for p in pool:
                if p["name"] in used:
                    continue
                if code == "MPB":
                    # 双月刊：文件月 = 封面起始月
                    ok = p["ym"] == it["start"]
                elif code == "PBS":
                    if p["suf"]:
                        want = PBS_SUF.get(p["suf"], "?")
                        if want == "?":
                            continue
                        ok = (p["ym"] == it["start"])
                        # 同月可能 ES(早春) 与 SP(春) 并存，用 key 区分
                        if ok and want == "early":
                            ok = it["key"].endswith("-early")
                        elif ok and want is None:
                            ok = not it["key"].endswith("-early")
                        if ok and p["suf"] == "SW":
                            ok = it["key"].endswith("-swimsuit")
                        elif ok:
                            ok = not it["key"].endswith("-swimsuit")
                    else:
                        ok = p["ym"] == it["end"] and not it["key"].endswith(("-early", "-swimsuit", "-extreme"))
                elif code == "IOB":
                    # 后缀必须与源文件版本一致：IOBE=Extreme，IOBS=Special，IOB=普通
                    ok = p["suf"] == it["kind"] and p["ym"] == it["start"]
                else:
                    ok = p["ym"] == it["start"]
                if ok:
                    cand.append(p)
            if not cand:
                problems.append((it, f"云端找不到对应文件（起始 {it['start']}）"))
                continue
            # 同条件多个时优先目录里 2025/2026 分年的那个（无所谓，取第一个）
            pick = cand[0]
            used.add(pick["name"])
            it.update({"cloud_name": pick["name"], "cloud_dir": pick["dir"]})
            pairs.append(it)

    return pairs, problems


def mark_md(it: dict) -> bool:
    """把下载入口写进 md：has_download + netdisk_file。已有链接的不动。"""
    md = CONTENT / it["slug"] / f"{it['key']}.md"
    text = md.read_text(encoding="utf-8")
    if "has_download: true" in text:
        return False
    if re.search(r"^download_url:", text, re.M):
        text = re.sub(r"^download_url:.*$", "has_download: true", text, count=1, flags=re.M)
    else:
        text = re.sub(r"^(download_pwd:.*)$", r"\1\nhas_download: true", text, count=1, flags=re.M)
    if "netdisk_file:" not in text:
        text = re.sub(r"^(download_pwd:.*)$",
                      lambda m: f'{m.group(1)}\nnetdisk_file: "{it["cloud_name"]}"',
                      text, count=1, flags=re.M)
    md.write_text(text, encoding="utf-8")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--delay", type=float, default=1.6)
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    pairs, problems = match_all()
    print(f"匹配成功 {len(pairs)} 期，问题 {len(problems)} 期\n")
    for it in pairs:
        print(f"  {it['slug']}/{it['key']:<32} <- {it['cloud_dir'].split('外文期刊/')[-1]}/{it['cloud_name']}")
    for it, why in problems:
        print(f"  [待处理] {it['slug']}/{it['key']:<28} {why}  ({it['label']})")

    if args.dry_run:
        return

    q = rs.Quark()
    done, failed = [], []
    for i, it in enumerate(pairs, 1):
        try:
            fid = q.find_file(it["cloud_dir"], it["cloud_name"])
            sid = q.share_file(fid, it["cloud_name"])
            it["share_id"] = sid
            print(f"  {i}/{len(pairs)} 建分享 {it['slug']}/{it['key']} -> {sid}", flush=True)
        except Exception as exc:  # noqa: BLE001
            failed.append({"key": f"{it['slug']}/{it['key']}", "error": str(exc)})
            print(f"  {i}/{len(pairs)} FAIL {it['slug']}/{it['key']} {exc}", flush=True)
        time.sleep(args.delay)

    print("\n校验…")
    idx = q.share_index()
    for it in pairs:
        sid = it.get("share_id")
        if not sid:
            continue
        rec = idx.get(sid)
        if not rec:
            failed.append({"key": f"{it['slug']}/{it['key']}", "error": "列表里找不到分享"})
            continue
        try:
            n = q.share_file_count(rec["pwd_id"])
        except Exception as exc:  # noqa: BLE001
            failed.append({"key": f"{it['slug']}/{it['key']}", "error": f"校验失败 {exc}"})
            continue
        if n <= 0:
            failed.append({"key": f"{it['slug']}/{it['key']}", "error": "文件数 0"})
            continue
        it["url"] = f"https://pan.quark.cn/s/{rec['pwd_id']}"
        done.append(it)
        print(f"  OK {it['slug']}/{it['key']:<32} {it['url']} n={n}", flush=True)
        time.sleep(0.3)

    OUT.write_text(json.dumps({"done": done, "failed": failed}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n成功 {len(done)}，失败 {len(failed)} -> {OUT}")

    if args.apply and done:
        n_md = sum(1 for it in done if mark_md(it))
        links = json.loads(LINKS.read_text(encoding="utf-8"))
        for it in done:
            k = f"{it['slug']}-{it['key']}"
            links[k] = {"url": it["url"], "pwd": ""}
        LINKS.write_text(json.dumps(links, ensure_ascii=False, indent=1), encoding="utf-8")
        bulk = [{"key": "i:" + k, "value": json.dumps(v, ensure_ascii=False)}
                for k, v in links.items()]
        (HERE / ".links_bulk.json").write_text(json.dumps(bulk, ensure_ascii=False, indent=0),
                                               encoding="utf-8")
        patch = [{"key": "i:" + f"{it['slug']}-{it['key']}",
                  "value": json.dumps({"url": it["url"], "pwd": ""}, ensure_ascii=False)}
                 for it in done]
        (HERE / ".links_patch.json").write_text(json.dumps(patch, ensure_ascii=False, indent=0),
                                                encoding="utf-8")
        print(f"已写回 .links_kv.json（{len(links)} 条）/ .links_bulk.json / .links_patch.json")
        print(f"md 写入下载入口 {n_md} 期")


if __name__ == "__main__":
    main()
