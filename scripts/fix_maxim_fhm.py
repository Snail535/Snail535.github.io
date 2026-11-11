# -*- coding: utf-8 -*-
"""把误挂在 Maxim 名下的 FHM 澳/新刊归位。

来源包把 2025-10 起的 FHM 澳大利亚/新西兰版命名为 Maxim_Australia_/Maxim_NewZealand_。
处理方式：
  · 澳大利亚 4 期（2025-10 ~ 2026-01）FHM 目录里没有 → 源文件改名搬进 FHM，站点条目改成 FHM；
  · 新西兰 7 期（2025-10 ~ 2026-04）FHM 里已有同一期 → 删掉 Maxim 这边的重复条目。
"""
import json, re, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = Path(r"E:/迅雷下载/英文杂志/原文档")
CONTENT = ROOT / "content" / "magazines"
THUMBS = ROOT / "static" / "thumbs" / "magazines"
DRY = False

MON = {m: i for i, m in enumerate(
    ["January","February","March","April","May","June","July","August",
     "September","October","November","December"], 1)}

MOVE = [  # (maxim 源文件, fhm 目标文件, 期次 key)
    (r"MAX\2025\Australia\Maxim_Australia_-_October_2025.pdf",
     r"FHM\2025\Australia\FHM_Australia_-_October_2025.pdf", "2025-10-australia"),
    (r"MAX\2025\Australia\Maxim_Australia_-_November_2025.pdf",
     r"FHM\2025\Australia\FHM_Australia_-_November_2025.pdf", "2025-11-australia"),
    (r"MAX\2025\Australia\Maxim_Australia_-_December_2025.pdf",
     r"FHM\2025\Australia\FHM_Australia_-_December_2025.pdf", "2025-12-australia"),
    (r"MAX\2026\Australia\Maxim_Australia_-_January_2026.pdf",
     r"FHM\2026\Australia\FHM_Australia_-_January_2026.pdf", "2026-01-australia"),
]
DROP = ["2025-10-new-zealand-newzealand", "2025-11-new-zealand-newzealand",
        "2025-12-new-zealand-newzealand", "2026-01-new-zealand-newzealand",
        "2026-02-new-zealand-newzealand", "2026-03-new-zealand-newzealand",
        "2026-04-new-zealand-newzealand"]


def patch_md(text, new_name):
    text = text.replace('magazine: "Maxim"', 'magazine: "FHM"')
    text = text.replace('magazine_slug: "maxim"', 'magazine_slug: "fhm"')
    text = text.replace("/thumbs/magazines/maxim/", "/thumbs/magazines/fhm/")
    text = re.sub(r'alt: "Maxim ', 'alt: "FHM ', text)
    text = re.sub(r'^file_name: ".*?"$', f'file_name: "{new_name}"', text, flags=re.M)
    return text


def main():
    # 1) 源文件搬到 FHM 目录
    for src_rel, dst_rel, key in MOVE:
        s, d = SRC / src_rel, SRC / dst_rel
        print(f"{'[dry] ' if DRY else ''}move {s.name} → {d.relative_to(SRC)}")
        if not DRY:
            if not s.exists():
                print("   ! 源文件不存在，跳过"); continue
            d.parent.mkdir(parents=True, exist_ok=True)
            if d.exists():
                print("   ! 目标已存在，跳过"); continue
            s.replace(d)

    # 2) 4 期 md 改挂到 FHM
    for _, dst_rel, key in MOVE:
        old = CONTENT / "maxim" / f"{key}.md"
        new = CONTENT / "fhm" / f"{key}.md"
        if not old.exists():
            print(f"   ! 缺 {old.name}"); continue
        txt = patch_md(old.read_text(encoding="utf-8"), Path(dst_rel).name)
        print(f"{'[dry] ' if DRY else ''}md   maxim/{key}.md → fhm/{key}.md")
        if not DRY:
            new.write_text(txt, encoding="utf-8")
            old.unlink()
            src_dir, dst_dir = THUMBS / "maxim" / key, THUMBS / "fhm" / key
            if src_dir.exists():
                if dst_dir.exists():
                    shutil.rmtree(dst_dir)
                shutil.move(str(src_dir), str(dst_dir))

    # 3) 新西兰重复条目删掉
    for key in DROP:
        md = CONTENT / "maxim" / f"{key}.md"
        print(f"{'[dry] ' if DRY else ''}drop maxim/{key}")
        if not DRY:
            if md.exists():
                md.unlink()
            d = THUMBS / "maxim" / key
            if d.exists():
                shutil.rmtree(d)

    # 4) 链接表跟着改名/删除
    lk_path = ROOT / "scripts" / ".links_kv.json"
    links = json.loads(lk_path.read_text(encoding="utf-8"))
    for _, _, key in MOVE:
        old_k, new_k = f"maxim-{key}", f"fhm-{key}"
        if old_k in links:
            print(f"links {old_k} → {new_k}")
            if not DRY:
                links[new_k] = links.pop(old_k)
    for key in DROP:
        k = f"maxim-{key}"
        if k in links:
            print(f"links 删除 {k}")
            if not DRY:
                links.pop(k)
    if not DRY:
        lk_path.write_text(json.dumps(links, ensure_ascii=False, indent=1), encoding="utf-8")
    print("done")


if __name__ == "__main__":
    main()
