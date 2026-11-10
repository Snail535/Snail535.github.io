# -*- coding: utf-8 -*-
"""列出仍缺网盘链接的期次。"""
import re
import pathlib

n = 0
for md in sorted(pathlib.Path("content/magazines").glob("*/*.md")):
    if md.name == "_index.md":
        continue
    t = md.read_text(encoding="utf-8")
    m = re.search(r'^download_url:[ \t]*(.*)$', t, re.M)
    val = (m.group(1) if m else "").strip().strip('"')
    if val.startswith("http"):
        continue
    n += 1

    def g(k):
        mm = re.search(r'^' + k + r':[ \t]*(.*)$', t, re.M)
        return (mm.group(1) if mm else "").strip().strip('"')

    print("  %-20s %-28s %s" % (g("magazine"), g("issue_label"), g("file_name")))
print("缺链接", n)
