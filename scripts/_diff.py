"""盘点源目录相对已收录 md 的新增/缺失期次（只读，不写任何文件）"""
import sys, glob, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import gen_magazines as g

reg = g.load_registry()
by_folder, mags = g.build_index(reg)
editions = g.build_editions(reg)

for d in sorted(g.ROOT_SRC.iterdir()):
    if d.is_dir() and g.match_mag(by_folder, d.name) is None:
        print(f"[new-folder] {d.name} 未登记")

records, skips = [], []
for pdf in sorted(g.ROOT_SRC.rglob("*.pdf")):
    rel = pdf.relative_to(g.ROOT_SRC)
    folder = rel.parts[0]
    mag = g.match_mag(by_folder, folder)
    if not mag:
        continue
    pub_part, date_part = g.split_publication_and_date(pdf.stem)
    parsed = g.parse_date_part(date_part)
    if not parsed:
        skips.append((mag["slug"], str(rel)))
        continue
    _, end, label = parsed
    y, m, d = end
    edition = g.detect_edition(pub_part, editions)
    if not edition:
        for part in rel.parts[1:-1]:
            edition = g.detect_edition(part, editions)
            if edition:
                break
    ed_slug = g.slugify(edition) if edition else ""
    variant = g.detect_variant(pub_part, date_part, mag, edition)
    v_slug = g.slugify(variant) if variant else ""
    issue = f"{y:04d}-{m:02d}" + (f"-{d:02d}" if d != 1 else "")
    key = issue + (f"-{ed_slug}" if ed_slug else "") + (f"-{v_slug}" if v_slug else "")
    if any(r["slug"] == mag["slug"] and r["key"] == key for r in records):
        skips.append((mag["slug"], str(rel) + "  [dupe key]"))
        continue
    records.append({"slug": mag["slug"], "key": key, "rel": str(rel)})

have = {}
for slug_dir in g.OUT_CONTENT.iterdir():
    if slug_dir.is_dir():
        have[slug_dir.name] = {p.stem for p in slug_dir.glob("*.md") if p.name != "_index.md"}

new_by = {}
stale = {}
for r in records:
    s = have.get(r["slug"], set())
    if r["key"] not in s:
        new_by.setdefault(r["slug"], []).append(r)

print(f"\n源目录共解析 {len(records)} 期")
if new_by:
    print("=== 新增 ===")
    total = 0
    for slug, rs in sorted(new_by.items()):
        total += len(rs)
        print(f"{slug:<20} {len(rs):>3} 期  {', '.join(sorted(x['key'] for x in rs))}")
    print(f"新增合计 {total} 期")
else:
    print("=== 无新增 ===")

print("\n=== 已收录但源目录已不存在（可能是改名/删除） ===")
for slug, keys in sorted(have.items()):
    cur = {r["key"] for r in records if r["slug"] == slug}
    gone = keys - cur
    if gone:
        print(f"{slug:<20} {len(gone):>3} 期  {', '.join(sorted(gone)[:8])}")

if skips:
    print("\n=== 跳过（解析不了 / key 冲突） ===")
    for s in skips[:40]:
        print("  ", s[0], s[1])
    if len(skips) > 40:
        print(f"   ... 还有 {len(skips) - 40} 条")
