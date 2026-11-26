# -*- coding: utf-8 -*-
"""为 11-25 新增 BBC Science Focus（BSF）各期建夸克分享并写回 md/links。

映射来源：md 的 file_name → 归档脚本 target_stem → cloud 路径。
用法：
    python scripts/build_shares_bsf.py --map-only
    python scripts/build_shares_bsf.py              # 建分享+校验
    python scripts/build_shares_bsf.py --apply-only # 用上次结果写回
"""
import argparse, json, os, re, sys, time, importlib.util
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CONTENT = ROOT / "content" / "magazines"
LINKS = HERE / ".links_kv.json"
TREE = HERE / ".cloud_tree.json"
OUT = HERE / ".new_shares_bsf.json"

MAGS = {"BSF": "bbc-science-focus"}
ARCHIVE = Path(r"E:\Document\Python程序\其他\杂志归档.py")


def load_archive_mod():
    spec = importlib.util.spec_from_file_location("archive_mod", str(ARCHIVE))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def safe_write(path, text):
    try:
        path.write_text(text, encoding="utf-8")
    except PermissionError:
        tmp = path.with_name(path.name + f".tmp{os.getpid()}")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)


def stem_from_fname(mod, abbr, fname):
    ym = re.search(r"(20\d{2})", fname)
    yr = ym.group(1) if ym else "UNKNOWN"
    return mod.target_stem(abbr, [yr], fname)


def build_map():
    mod = load_archive_mod()
    mp = {}
    try:
        have = set(json.load(open(LINKS, encoding="utf-8")))
    except Exception:
        have = set()
    for abbr, slug in MAGS.items():
        for md in sorted((CONTENT / slug).glob("*.md")):
            if md.name == "_index.md":
                continue
            text = md.read_text(encoding="utf-8")
            mm = re.search(r'^file_name:\s*"?(.*?)"?\s*$', text, re.M)
            if not mm:
                print("  [缺file_name]", md.name)
                continue
            fname = mm.group(1)
            stem = stem_from_fname(mod, abbr, fname)
            if not stem:
                print("  [解析失败]", fname)
                continue
            yr = re.search(r"(20\d{2})", fname).group(1)
            cloud_dir = f"外文期刊/月刊/{abbr}/{yr}"
            key = f"{slug}-{md.stem}"
            if key in have:
                continue  # 已有分享，不重复建
            mp[key] = (cloud_dir, stem + ".jpg", md, slug, md.stem)
    return mp


def check_tree(mp):
    tree = json.load(open(TREE, encoding="utf-8"))
    have = {(r["dir"], r["name"]) for r in tree}
    return [k for k, (d, n, *_) in mp.items() if (d, n) not in have]


def mark_md(md_path, cloud_name):
    text = md_path.read_text(encoding="utf-8")
    if "has_download: true" not in text:
        if re.search(r"^download_url:", text, re.M):
            text = re.sub(r"^download_url:.*$", "has_download: true", text, count=1, flags=re.M)
        else:
            text = re.sub(r"^(download_pwd:.*)$", r"\1\nhas_download: true", text, count=1, flags=re.M)
    if re.search(r"^netdisk_file:", text, re.M):
        text = re.sub(r"^netdisk_file:.*$", f'netdisk_file: "{cloud_name}"', text, count=1, flags=re.M)
    else:
        text = re.sub(r"^(download_pwd:.*)$",
                      lambda m: f'{m.group(1)}\nnetdisk_file: "{cloud_name}"',
                      text, count=1, flags=re.M)
    safe_write(md_path, text)


def write_back(ok):
    n = 0
    for it in ok:
        mark_md(Path(it["md_path"]), it["cloud"].rsplit("/", 1)[1])
        n += 1
    links = json.load(open(LINKS, encoding="utf-8"))
    for it in ok:
        links[it["key"]] = {"url": it["url"], "pwd": ""}
    safe_write(LINKS, json.dumps(links, ensure_ascii=False, indent=1))
    bulk = [{"key": "i:" + k, "value": json.dumps(v, ensure_ascii=False)} for k, v in links.items()]
    safe_write(HERE / ".links_bulk.json", json.dumps(bulk, ensure_ascii=False, indent=0))
    print(f"[apply] 写回 md {n} 条、links 共 {len(links)} 条")


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
        data = json.load(open(OUT, encoding="utf-8"))
        write_back(data["done"])
        return

    mp = build_map()
    print("待处理", len(mp), "期")
    missing = check_tree(mp)
    for m in missing:
        print("  [缺]", m)
    if missing:
        sys.exit(f"云盘缺 {len(missing)} 个，先不建分享")
    print("云盘校验通过", len(mp), "/", len(mp))
    if args.map_only:
        for k, (d, n, *_) in sorted(mp.items()):
            print(" ", k, d + "/" + n)
        return

    import repair_shares as rs
    q = rs.Quark()
    try:
        q.s.trust_env = False
    except Exception:
        pass
    done, failed = [], []
    for i, (k, (d, n, mdp, slug, key)) in enumerate(sorted(mp.items()), 1):
        try:
            fid = q.find_file(d, n)
            sid = q.share_file(fid, n)
            done.append({"key": k, "share_id": sid, "cloud": f"{d}/{n}", "md_path": str(mdp)})
            print(f"  {i}/{len(mp)} 建分享 {k} -> {sid}", flush=True)
        except Exception as exc:
            failed.append({"key": k, "error": str(exc)})
            print(f"  {i}/{len(mp)} FAIL {k} {exc}", flush=True)
        time.sleep(args.delay)

    print("\n校验…")
    idx = q.share_index()
    ok = []
    for it in done:
        rec = idx.get(it["share_id"])
        if not rec:
            failed.append({"key": it["key"], "error": "列表找不到分享"})
            continue
        try:
            cnt = q.share_file_count(rec["pwd_id"])
        except Exception as exc:
            failed.append({"key": it["key"], "error": f"校验失败 {exc}"})
            continue
        if cnt != 1:
            failed.append({"key": it["key"], "error": f"文件数{cnt}"})
            continue
        it["url"] = f"https://pan.quark.cn/s/{rec['pwd_id']}"
        ok.append(it)
        print(f"  OK {it['key']:<44} {it['url']}", flush=True)
        time.sleep(0.3)

    safe_write(OUT, json.dumps({"done": ok, "failed": failed}, ensure_ascii=False, indent=1))
    print(f"\n成功 {len(ok)}，失败 {len(failed)} -> {OUT}")
    if args.apply and ok:
        write_back(ok)


if __name__ == "__main__":
    main()
