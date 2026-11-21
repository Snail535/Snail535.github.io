# -*- coding: utf-8 -*-
"""为 11-22 新增两刊 SN/NG 共 104 期建夸克分享并写回。

映射来源：data/issue_overrides.yaml 的 cloud 字段（已为 104 期全部写好）。
流程参考 build_shares_batch5.py。
用法：
    python scripts/build_shares_sn_ng.py --map-only   # 只校验映射
    python scripts/build_shares_sn_ng.py              # 建分享+校验 -> .new_shares_sn_ng.json
    python scripts/build_shares_sn_ng.py --apply-only # 用上次结果写回
"""
import argparse, json, os, re, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CONTENT = ROOT / "content" / "magazines"
OVR = ROOT / "data" / "issue_overrides.yaml"
LINKS = HERE / ".links_kv.json"
TREE = HERE / ".cloud_tree.json"
OUT = HERE / ".new_shares_sn_ng.json"

def safe_write(path, text):
    try:
        path.write_text(text, encoding="utf-8")
    except PermissionError:
        tmp = path.with_name(path.name + f".tmp{os.getpid()}")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)

def build_map():
    import yaml
    ov = yaml.safe_load(OVR.read_text(encoding="utf-8")) or {}
    mp = {}
    for rel, item in ov.items():
        if not (rel.startswith("SN/") or rel.startswith("NG/")):
            continue
        cloud = (item or {}).get("cloud")
        if not cloud:
            continue
        # 从 cloud 路径推 slug/key：SN->science-news, NG->national-geographic
        parts = cloud.split("/")  # 外文期刊/周刊/SN/2024/xxx.jpg
        mag_dir = parts[2]
        fname = parts[-1]
        slug = "science-news" if mag_dir == "SN" else "national-geographic"
        # stem -> md key：从 override 的 key/edition 反查
        key = item.get("key")
        ed = item.get("edition")
        # md 里 edition slug 是 usa/uk；override key 已经含 edition slug
        md_path = CONTENT / slug / f"{key}.md"
        if not md_path.exists():
            print("  [缺md]", md_path.name); continue
        # netdisk_file 用图种名（fname）
        mp[f"{slug}-{key}"] = ("/".join(parts[:-1]), fname, md_path, slug, key)
    return mp

def check_tree(mp):
    tree = json.load(open(TREE, encoding="utf-8"))
    have = {(r["dir"], r["name"]) for r in tree}
    return [k for k,(d,n,*_) in mp.items() if (d,n) not in have]

def mark_md(md_path, cloud_name):
    text = md_path.read_text(encoding="utf-8")
    if "has_download: true" not in text:
        if re.search(r"^download_url:", text, re.M):
            text = re.sub(r"^download_url:.*$", "has_download: true", text, count=1, flags=re.M)
        else:
            text = re.sub(r"^(download_pwd:.*)$", r"\1\nhas_download: true", text, count=1, flags=re.M)
    # netdisk_file
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
        mark_md(Path(it["md_path"]), it["cloud"].rsplit("/",1)[1]); n += 1
    links = json.load(open(LINKS, encoding="utf-8"))
    for it in ok:
        links[it["key"]] = {"url": it["url"], "pwd": ""}
    safe_write(LINKS, json.dumps(links, ensure_ascii=False, indent=1))
    bulk = [{"key": "i:"+k, "value": json.dumps(v, ensure_ascii=False)} for k,v in links.items()]
    safe_write(HERE / ".links_bulk.json", json.dumps(bulk, ensure_ascii=False, indent=0))
    print(f"[apply] 写回 md {n} 条、links 共 {len(links)} 条")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--apply-only", action="store_true")
    ap.add_argument("--delay", type=float, default=1.6)
    ap.add_argument("--map-only", action="store_true")
    args = ap.parse_args()
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass

    if args.apply_only:
        data = json.load(open(OUT, encoding="utf-8"))
        write_back(data["done"]); return

    mp = build_map()
    print("待处理", len(mp), "期")
    missing = check_tree(mp)
    for m in missing: print("  [缺]", m)
    if missing:
        sys.exit(f"云盘缺 {len(missing)} 个，先不建分享")
    print("云盘校验通过", len(mp), "/", len(mp))
    if args.map_only:
        for k,(d,n,*_) in sorted(mp.items()): print(" ", k, d+"/"+n)
        return

    import repair_shares as rs
    q = rs.Quark()
    # 绕开沙箱代理抖动
    try: q.s.trust_env = False
    except Exception: pass
    done, failed = [], []
    for i,(k,(d,n,mdp,slug,key)) in enumerate(sorted(mp.items()),1):
        try:
            fid = q.find_file(d, n)
            sid = q.share_file(fid, n)
            done.append({"key":k, "share_id":sid, "cloud":f"{d}/{n}", "md_path":str(mdp)})
            print(f"  {i}/{len(mp)} 建分享 {k} -> {sid}", flush=True)
        except Exception as exc:
            failed.append({"key":k,"error":str(exc)})
            print(f"  {i}/{len(mp)} FAIL {k} {exc}", flush=True)
        time.sleep(args.delay)

    print("\n校验…")
    idx = q.share_index()
    ok = []
    for it in done:
        rec = idx.get(it["share_id"])
        if not rec:
            failed.append({"key":it["key"],"error":"列表找不到分享"}); continue
        try:
            cnt = q.share_file_count(rec["pwd_id"])
        except Exception as exc:
            failed.append({"key":it["key"],"error":f"校验失败 {exc}"}); continue
        if cnt != 1:
            failed.append({"key":it["key"],"error":f"文件数{cnt}"}); continue
        it["url"] = f"https://pan.quark.cn/s/{rec['pwd_id']}"
        ok.append(it)
        print(f"  OK {it['key']:<44} {it['url']}", flush=True)
        time.sleep(0.3)

    safe_write(OUT, json.dumps({"done":ok,"failed":failed}, ensure_ascii=False, indent=1))
    print(f"\n成功 {len(ok)}，失败 {len(failed)} -> {OUT}")
    if args.apply and ok:
        write_back(ok)

if __name__ == "__main__":
    main()
