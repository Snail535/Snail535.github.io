# -*- coding: utf-8 -*-
"""把各期网盘分享链接导出成 Excel 表格，便于查阅与核对。

数据来源：content/magazines/<slug>/<期次>.md 的 front matter
输出：links.xlsx（含「全部期次」与「按刊物统计」两个表）

用法：
    python scripts/export_links.py              # 输出 links.xlsx
    python scripts/export_links.py -o 我的表.xlsx
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
CONTENT = HERE / "content" / "magazines"

COLS = ["序号", "刊物", "年份", "期次", "国家 / 专题", "网盘文件名",
        "分享链接", "提取码", "页数", "大小", "状态"]


def grab(text: str, key: str) -> str:
    m = re.search(rf"^{key}:[ \t]*(.*)$", text, re.M)
    return (m.group(1) if m else "").strip().strip('"').strip("'")


def collect():
    rows = []
    for md in sorted(CONTENT.glob("*/*.md")):
        if md.name == "_index.md":
            continue
        t = md.read_text(encoding="utf-8")
        url = grab(t, "download_url")
        rows.append({
            "key": f"{md.parent.name}/{md.stem}",
            "magazine": grab(t, "magazine"),
            "issue": grab(t, "issue_label"),
            "edition": grab(t, "edition") or (
                grab(t, "issue_label").split("·")[-1].strip()
                if "·" in grab(t, "issue_label") else ""),
            "year": grab(t, "date")[:4],
            "netdisk": grab(t, "netdisk_file"),
            "url": url if url.startswith("http") else "",
            "pwd": grab(t, "download_pwd") or "无",
            "pages": grab(t, "pages"),
            "size": grab(t, "file_size"),
            "date": grab(t, "date")[:10],
        })
    # 刊物按期数多的在前，同一刊物内新期次在前
    cnt = {}
    for r in rows:
        cnt[r["magazine"]] = cnt.get(r["magazine"], 0) + 1
    rows.sort(key=lambda r: (-cnt[r["magazine"]], r["magazine"]))
    rows.sort(key=lambda r: (-cnt[r["magazine"]], r["date"]), reverse=False)
    out, seen = [], {}
    for r in rows:
        seen.setdefault(r["magazine"], []).append(r)
    for mag in sorted(seen, key=lambda m: -cnt[m]):
        out += sorted(seen[mag], key=lambda r: r["date"], reverse=True)
    return out


def write_xlsx(rows, out: Path):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "全部期次"

    head_fill = PatternFill("solid", fgColor="1F3B4D")
    head_font = Font(color="FFFFFF", bold=True, size=11)
    thin = Side(style="thin", color="D9D9D9")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    ws.append(COLS)
    for c in ws[1]:
        c.fill = head_fill
        c.font = head_font
        c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 24

    for i, r in enumerate(rows, 1):
        ws.append([i, r["magazine"], r["year"], r["issue"], r["edition"],
                   r["netdisk"], r["url"], r["pwd"], r["pages"], r["size"],
                   "已建分享" if r["url"] else "待补"])

    for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
        for c in row:
            c.border = border
            c.alignment = Alignment(vertical="center")
        # 链接列做成可点
        link = row[6]
        if link.value:
            link.hyperlink = link.value
            link.font = Font(color="0563C1", underline="single")
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
        if not row[6].value:
            row[10].font = Font(color="C00000", bold=True)

    widths = [6, 20, 8, 30, 16, 18, 34, 8, 7, 10, 11]
    for n, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(n)].width = w
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(COLS))}{ws.max_row}"

    # 统计页
    ws2 = wb.create_sheet("按刊物统计")
    ws2.append(["刊物", "期数", "已有链接", "待补"])
    for c in ws2[1]:
        c.fill = head_fill
        c.font = head_font
        c.alignment = Alignment(horizontal="center")
    stat = {}
    for r in rows:
        s = stat.setdefault(r["magazine"], [0, 0])
        s[0] += 1
        s[1] += 1 if r["url"] else 0
    for mag in sorted(stat, key=str.lower):
        tot, ok = stat[mag]
        ws2.append([mag, tot, ok, tot - ok])
    ws2.append(["合计", len(rows), sum(v[1] for v in stat.values()),
                len(rows) - sum(v[1] for v in stat.values())])
    for c in ws2[ws2.max_row]:
        c.font = Font(bold=True)
    for n, w in enumerate([22, 8, 10, 8], 1):
        ws2.column_dimensions[get_column_letter(n)].width = w
    for row in ws2.iter_rows(min_row=1, max_row=ws2.max_row):
        for c in row:
            c.border = border
            c.alignment = Alignment(horizontal="center", vertical="center")
            if c.column == 1:
                c.alignment = Alignment(horizontal="left", vertical="center")

    wb.save(out)


def write_csv(rows, out: Path):
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLS)
        for i, r in enumerate(rows, 1):
            w.writerow([i, r["magazine"], r["year"], r["issue"], r["edition"],
                        r["netdisk"], r["url"], r["pwd"], r["pages"], r["size"],
                        "已建分享" if r["url"] else "待补"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default="links_table.xlsx")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    rows = collect()
    out = Path(args.out)
    if not out.is_absolute():
        out = HERE / out

    write_xlsx(rows, out)
    write_csv(rows, out.with_suffix(".csv"))

    ok = sum(1 for r in rows if r["url"])
    print(f"已导出 {out}：{len(rows)} 期，有链接 {ok} 期，待补 {len(rows) - ok} 期")
    print(f"同时导出 {out.with_suffix('.csv').name}（UTF-8 BOM，Excel 可直接打开）")


if __name__ == "__main__":
    main()
