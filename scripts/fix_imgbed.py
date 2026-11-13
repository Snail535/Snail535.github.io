"""把指向 .pdf.sssEFs 老档的期次改成指向「月刊」里的图种 .jpg。

用法：
  python scripts/fix_imgbed.py --dry-run
  python scripts/fix_imgbed.py --apply [--delay 3] [--only maxim,kandy]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import repair_shares as rs  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CONTENT = ROOT / "content" / "magazines"
TREE = HERE / ".cloud_tree.json"
LINKS = HERE / ".links_kv.json"
PATCH_OUT = HERE / ".links_imgbed.json"
FAILED_OUT = HERE / ".fix_imgbed_failed.json"

CODES = {
    "maxim": "MAX",
    "kandy": "KDY",
    "exotic": "EXO",
    "inciter": "INC",
    "inside-out-babes": "IOB",
    "lingerie-plus": "LGP",
    "bossing": "BOS",
    "rhk": "RHK",
    "ric": "RIC",
    "penthouse": "PNT",
    "fhm": "FHM",
    "playboy": "PLB",
    "boudoir-inspiration": "BOU",
    "tempting-photo": "TMP",
    "mancave-playbabes": "MPB",
}
COUNTRY_CODES = {"MAX", "FHM", "PLB", "PNT"}
ISSUE_CODES = {"RIC", "RHK"}
ED_MAP = {
    "Australia": "AU", "New Zealand": "NZ", "USA": "US", "UK": "UK",
    "Canada": "CA", "France": "FR", "India": "IN", "Mexico": "MX",
    "Sweden": "SE", "South Africa": "ZA", "Africa": "AF", "Denmark": "DK",
    "Norway": "NO", "Finland": "FI", "Philippines": "TT",
}
# BOU 五个子系列的后缀（按顺序匹配，越具体的放前面）
BOU_RULES = [
    ("lingerie", "LI"),
    ("artistic", "AN"),
    ("nude", "AN"),
    ("black-and-white", "BW"),
    ("black and white", "BW"),
    ("boudoir", "BI"),
]
SEASONS = {"SP": "spring", "SU": "summer", "FA": "fall", "WI": "winter"}


def build_index(rows):
    idx = {}
    for r in rows:
        name = r["name"]
        if not name.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        if not r["dir"].startswith("外文期刊/月刊/"):
            continue
        parts = r["dir"].split("/")
        code = parts[2] if len(parts) > 2 else ""
        stem = os.path.splitext(name)[0].upper()
        if stem.startswith(code):
            rest = stem[len(code):]
        else:
            rest = re.sub(r"^[A-Z]+", "", stem)   # 前缀与目录名不一致时按字母前缀剥离
        m = re.fullmatch(r"([A-Z]{0,2}?)(\d{2,6})", rest)
        if not m:
            continue
        suf, num = m.group(1), m.group(2)
        code_use = code
        rec = {"name": name, "dir": r["dir"], "suf": suf, "num": num,
               "ym": None, "issue": None}
        if len(num) == 4:
            rec["ym"] = (2000 + int(num[:2]), int(num[2:]))
        elif len(num) == 3:
            rec["issue"] = int(num)
        elif len(num) == 6:
            rec["ym"] = (2000 + int(num[:2]), int(num[2:4]))
        elif len(num) == 2:
            rec["ym"] = (2000 + int(num), 0)
        idx.setdefault(code_use, []).append(rec)
    return idx


def load_md(slug):
    out = []
    for f in sorted(glob.glob(str(CONTENT / slug / "*.md"))):
        p = Path(f)
        if p.name == "_index.md":
            continue
        meta = {}
        for line in p.read_text(encoding="utf-8").splitlines():
            for k in ("issue", "edition", "netdisk_file", "issue_label", "file_name"):
                if line.startswith(k + ":"):
                    meta[k] = line.split(":", 1)[1].strip().strip('"')
        out.append({"slug": slug, "path": p, "key": p.stem, **meta})
    return out


def want_ym(issue):
    m = re.match(r"(\d{4})-(\d{2})", issue or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


MONTH_WORDS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12, "winter": 12, "spring": 3, "summer": 6, "fall": 9, "autumn": 9,
}


def month_from_name(fn):
    low = fn.lower()
    best = None
    for w, m in MONTH_WORDS.items():
        i = low.find(w)
        if i >= 0 and (best is None or i < best[0]):
            best = (i, m)
    return best[1] if best else None


def suffix_months(pool, suf, year):
    return sorted({r["ym"][1] for r in pool
                   if r["suf"] == suf and r["ym"] and r["ym"][0] == year})


def allow_backtrack(pool, suf, year):
    """该版本是否可能用「起始月」命名：双月刊（月份间隔基本都是 2）或全年只一期。"""
    ms = suffix_months(pool, suf, year)
    if len(ms) <= 1:
        return True
    gaps = [b - a for a, b in zip(ms, ms[1:])]
    return sum(1 for g in gaps if g == 2) >= len(gaps) * 0.6


def pick(md, pool, code):
    fn = md.get("netdisk_file", "") or md.get("file_name", "")
    m = re.search(r"Issue[_\s]*(\d{1,4})", fn, re.I)
    issue_no = int(m.group(1)) if m else None

    if code in ISSUE_CODES:
        if issue_no is None:
            return None, "无期号"
        hits = [r for r in pool if r["issue"] == issue_no]
        if len(hits) == 1:
            return hits[0], "issue %d" % issue_no
        if len(hits) > 1:
            return hits[0], "issue %d(多解)" % issue_no
        return None, "图种无 issue %d" % issue_no

    ym = want_ym(md.get("issue", ""))
    if not ym:
        return None, "无期次"
    label = (fn + " " + md.get("issue_label", "") + " " + md["key"].replace("-", " ")).lower()

    # 周年特刊：KDYAN22 / KDYAN26（只有年份，没有月份）
    if "anniversary" in label or re.search(r"Anniversary", fn, re.I):
        hits = [r for r in pool if r["suf"] == "AN" and r["ym"] and r["ym"][0] == ym[0]]
        if hits:
            return hits[0], "%d 周年" % ym[0]
        return None, "图种无 %d 周年" % ym[0]

    season = next((s for s, w in SEASONS.items() if w in label), None)
    # 版本后缀：IOB 的 Special(S) / Extreme(E)
    variant = "E" if "extreme" in label else ("S" if "special" in label else "")
    # 国家版后缀：FHM / PLB / MAX / PNT 按 edition 精确挑
    ed_suf = ED_MAP.get(md.get("edition", ""), "")
    ed_name = md.get("edition", "")
    # 国家版刊物：edition 有值但网盘里没有这个国家代码 → 该版本没上传，不能拿别国凑
    if code in COUNTRY_CODES and ed_name and not ed_suf:
        return None, "网盘无 %s 版" % ed_name
    # BOU 子系列：Lingerie Inspiration / Artistic Nude / Black and White / Boudoir
    bou_suf = ""
    if code == "BOU":
        for kw, s in BOU_RULES:
            if kw in label:
                bou_suf = s
                break
    tries = [ym]
    mm0 = ym[1]
    # 合刊（September-October）按文件名里的第一个月找
    fm = month_from_name(fn)
    if fm and (ym[0], fm) != ym:
        tries.append((ym[0], fm))
    # 双月刊（Maxim USA、Playboy 菲律宾等）图种用「起始月」命名，md 存的是结束月：
    # 只有当目标月完全没有图种时才回退，避免把别的版本硬凑过来
    for back in (1, 2):
        if mm0 > back:
            tries.append((ym[0], ym[1] - back))

    for yy, mm in tries:
        cands = [r for r in pool if r["ym"] == (yy, mm)]
        if not cands:
            continue
        if ed_suf:
            # 同月多国版本：只认对应国家后缀
            hit = [r for r in cands if r["suf"] == ed_suf]
            if hit:
                return hit[0], "%d-%02d·%s" % (yy, mm, ed_suf)
            # 该国家版是双月刊（间隔基本为 2 个月）或全年只有一期时，图种记的是起始月
            if allow_backtrack(pool, ed_suf, yy):
                continue
            return None, "图种无 %d-%02d·%s" % (yy, mm, ed_suf)
        if bou_suf:
            hit = [r for r in cands if r["suf"] == bou_suf]
            if hit:
                return hit[0], "%d-%02d·%s" % (yy, mm, bou_suf)
            return None, "图种无 %d-%02d·%s" % (yy, mm, bou_suf)
        if variant:
            pref = [r for r in cands if r["suf"] == variant]
            if pref:
                return pref[0], "%d-%02d·%s" % (yy, mm, variant)
            return None, "图种无 %d-%02d·%s" % (yy, mm, variant)
        if season:
            pref = [r for r in cands if r["suf"] == season]
            if pref:
                return pref[0], "%d-%02d" % (yy, mm)
        plain = [r for r in cands if not r["suf"]]
        return (plain or cands)[0], "%d-%02d" % (yy, mm)
    return None, "图种无 %d-%02d" % (ym[0], ym[1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--delay", type=float, default=1.6)
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    if not args.apply:
        args.dry_run = True
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    idx = build_index(json.loads(TREE.read_text(encoding="utf-8")))
    todo, unmatched = [], []
    slugs = [s.strip() for s in args.only.split(",") if s.strip()] or list(CODES)
    taken = set()
    for slug in slugs:
        code = CODES.get(slug)
        if not code:
            continue
        for md in load_md(slug):
            cur = md.get("netdisk_file", "")
            if cur and not cur.lower().endswith(".sssefs"):
                continue
            # 一个图种只能给一期用，先到先得，避免两期指向同一个文件
            pool = [r for r in idx.get(code, []) if r["name"] not in taken]
            rec, why = pick(md, pool, code)
            if rec:
                taken.add(rec["name"])
                todo.append({"md": md, "rec": rec, "why": why})
            else:
                unmatched.append((slug, md["key"], cur, why))

    print("待改：%d   未匹配：%d" % (len(todo), len(unmatched)))
    for it in todo[:12]:
        print("  ", it["md"]["key"], "->", it["rec"]["name"], "|", it["why"])
    if unmatched:
        print("--- 未匹配 ---")
        for u in unmatched:
            print("  ", u[0], u[1], "|", u[2], "|", u[3])
    if args.dry_run or not todo:
        return

    q = rs.Quark()
    for i, it in enumerate(todo, 1):
        md, rec = it["md"], it["rec"]
        try:
            fid = q.find_file(rec["dir"], rec["name"])
            it["share_id"] = q.share_file(fid, rec["name"])
            print("[%d/%d] %s/%s -> %s" % (i, len(todo), md["slug"], md["key"],
                                           it["share_id"]), flush=True)
        except Exception as exc:
            it["error"] = str(exc)[:150]
            print("[%d/%d] FAIL %s/%s %s" % (i, len(todo), md["slug"], md["key"], exc),
                  flush=True)
        time.sleep(args.delay)

    print("\n校验…", flush=True)
    index = q.share_index()
    done, failed = [], []
    for it in todo:
        md, rec = it["md"], it["rec"]
        sid = it.get("share_id")
        key = "%s/%s" % (md["slug"], md["key"])
        if not sid:
            failed.append({"key": key, "file": rec["name"], "error": it.get("error", "建分享失败")})
            continue
        r = index.get(sid)
        if not r:
            failed.append({"key": key, "file": rec["name"], "error": "列表里找不到分享"})
            continue
        try:
            n = q.share_file_count(r["pwd_id"])
        except Exception as exc:
            failed.append({"key": key, "file": rec["name"], "error": "校验失败 %s" % exc})
            continue
        if n <= 0:
            failed.append({"key": key, "file": rec["name"], "error": "文件数 0"})
            continue
        it["url"] = "https://pan.quark.cn/s/%s" % r["pwd_id"]
        done.append(it)
        print("  OK %-36s n=%d %s" % (key, n, it["url"]), flush=True)
        time.sleep(0.3)

    links = json.loads(LINKS.read_text(encoding="utf-8")) if LINKS.exists() else {}
    patch = []
    for it in done:
        md = it["md"]
        text = md["path"].read_text(encoding="utf-8")
        name = it["rec"]["name"]
        if re.search(r"^netdisk_file:", text, re.M):
            text = re.sub(r"^netdisk_file:.*$", 'netdisk_file: "%s"' % name,
                          text, count=1, flags=re.M)
        else:
            # 新生成的 md 没有这个字段，插到 download_pwd 之后（front matter 末尾）
            text = re.sub(r"^(download_pwd:.*)$",
                          lambda m: '%s\nnetdisk_file: "%s"' % (m.group(1), name),
                          text, count=1, flags=re.M)
        if "has_download: true" not in text:
            if re.search(r"^has_download:", text, re.M):
                text = re.sub(r"^has_download:.*$", "has_download: true", text, count=1, flags=re.M)
            else:
                text = re.sub(r"^(download_pwd:.*)$",
                              r"\1\nhas_download: true", text, count=1, flags=re.M)
        md["path"].write_text(text, encoding="utf-8")
        k = "%s-%s" % (md["slug"], md["key"])
        val = {"url": it["url"], "pwd": ""}
        links[k] = val
        patch.append({"key": "i:" + k, "value": json.dumps(val, ensure_ascii=False)})

    LINKS.write_text(json.dumps(links, ensure_ascii=False, indent=1), encoding="utf-8")
    PATCH_OUT.write_text(json.dumps(patch, ensure_ascii=False, indent=0), encoding="utf-8")
    bulk = [{"key": "i:" + k, "value": json.dumps(v, ensure_ascii=False)}
            for k, v in links.items()]
    (HERE / ".links_bulk.json").write_text(json.dumps(bulk, ensure_ascii=False, indent=0),
                                           encoding="utf-8")
    FAILED_OUT.write_text(json.dumps(failed, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n成功 %d / 失败 %d" % (len(done), len(failed)))
    print("md 已改 %d，KV 补丁 %d 条，全量 %d 条" % (len(done), len(patch), len(bulk)))


if __name__ == "__main__":
    main()
