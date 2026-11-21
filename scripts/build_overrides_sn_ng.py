# -*- coding: utf-8 -*-
"""为 11-22 新增两刊 SN(Science News)/NG(National Geographic) 生成 issue_overrides 条目。

stem -> 日期规则（与 B 线 杂志归档.py 的 MANUAL 一致）：
  SN241005 -> 2024-10-05   SN2508 -> 2025-08(无日)   SN080816 -> 2008-08-16
  NGUS2404 -> 2024-04 USA  NGUK2603 -> 2026-03 UK
输出追加到 data/issue_overrides.yaml（先备份）。
"""
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SRC = Path(r"E:\迅雷下载\英文杂志\原文档")
B_LINE = Path(r"E:\Document\Python程序\其他\_manual_block_1121.txt")
OVR = ROOT / "data" / "issue_overrides.yaml"

MONTH_FULL = {1:"January",2:"February",3:"March",4:"April",5:"May",6:"June",
              7:"July",8:"August",9:"September",10:"October",11:"November",12:"December"}

def parse_manual():
    text = B_LINE.read_text(encoding="utf-8")
    out = {"SN": {}, "NG": {}}
    for m in re.finditer(r"\('(SN|NG)', '([^']+)'\): '([A-Z0-9]+)'", text):
        mag, fn, stem = m.group(1), m.group(2), m.group(3)
        out[mag][fn] = stem
    return out

def sn_date(stem):
    # SNyymmdd(8位) 或 SNyymm(6位)
    d = stem[2:]
    if len(d) == 6:
        return 2000+int(d[:2]), int(d[2:4]), int(d[4:6])
    if len(d) == 4:
        return 2000+int(d[:2]), int(d[2:4]), 1
    return None

def ng_date(stem):
    # NGUS2404 / NGUK2603
    m = re.fullmatch(r"NG(US|UK)(\d{2})(\d{2})", stem)
    if not m: return None, None, None
    country = "USA" if m.group(1)=="US" else "UK"
    return 2000+int(m.group(2)), int(m.group(3)), country

def main():
    manual = parse_manual()
    print("SN", len(manual["SN"]), "NG", len(manual["NG"]))
    lines = []
    problems = []
    # SN
    for fn, stem in sorted(manual["SN"].items()):
        pdfs = list(SRC.glob("SN/**/" + fn))
        if not pdfs:
            problems.append("SN 找不到 " + fn); continue
        pdf = pdfs[0]
        y, mo, d = sn_date(stem)
        if not y:
            problems.append("SN 日期解析失败 " + stem); continue
        rel = pdf.relative_to(SRC).as_posix()
        date = f"{y:04d}-{mo:02d}" + (f"-{d:02d}" if d!=1 else "")
        label = f"{y} 年 {mo} 月" + (f" {d} 日" if d!=1 else "")
        key = date
        cloud = f"外文期刊/周刊/SN/{y:04d}/{stem}.jpg"
        lines += [f'"{rel}":', f'  date: "{date}"', f'  key: "{key}"',
                  f'  label: "{label}"', f'  cloud: "{cloud}"', ""]
    # NG
    for fn, stem in sorted(manual["NG"].items()):
        pdfs = list(SRC.glob("NG/**/" + fn))
        if not pdfs:
            problems.append("NG 找不到 " + fn); continue
        pdf = pdfs[0]
        y, mo, country = ng_date(stem)
        if not y:
            problems.append("NG 日期解析失败 " + stem); continue
        rel = pdf.relative_to(SRC).as_posix()
        date = f"{y:04d}-{mo:02d}"
        label = f"{y} 年 {mo} 月"
        ed = country.lower()  # usa / uk -> edition slug
        key = f"{date}-{ed}"
        cloud = f"外文期刊/月刊/NG/{y:04d}/{country}/{stem}.jpg"
        lines += [f'"{rel}":', f'  date: "{date}"', f'  key: "{key}"',
                  f'  label: "{label}"', f'  edition: "{country}"',
                  f'  cloud: "{cloud}"', ""]
    if problems:
        print("问题:"); [print(" ", p) for p in problems]; return 1
    block = "\n".join(lines)
    out = HERE / "_overrides_sn_ng.txt"
    out.write_text(block, encoding="utf-8")
    print("已生成", out, "条目", block.count('"\n') if False else sum(1 for l in lines if re.match(r'^".+":$', l)))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
