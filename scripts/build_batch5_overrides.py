# -*- coding: utf-8 -*-
"""生成 data/issue_overrides.yaml。

背景：不少 PDF 的文件名里没有月份（只有期号），或与既有页面的 key 规则不一致。
这里按「本地 PDF → 期次 key → 夸克云盘文件」三方对齐，产出显式覆盖表。

云盘命名规律（来自 scripts/.cloud_tree.json）：
    LHE{期号}.jpg          期号制（月刊，期号连续）
    SPD/DPD/CTD/ILE/CRA/CRP/SPB {YY}{MM}.jpg   月份制
    DPD{YY}N{NN}.jpg       期号制（备选命名）
    IOB/LGP 的 Special 版本用 S 前缀；BOU/KDY/PBS 各有主题前缀
"""
from __future__ import annotations

import os
import re
from collections import OrderedDict

SRC = r"E:\迅雷下载\英文杂志\原文档"
OUT = r"E:\BlogWork\myblog\data\issue_overrides.yaml"

ov: "OrderedDict[str, dict]" = OrderedDict()


def add(rel: str, date=None, key=None, label=None, cloud=None, skip=False, edition=None):
    assert rel not in ov, rel
    item = {}
    if date:
        item["date"] = date
    if key:
        item["key"] = key
    if label:
        item["label"] = label
    if edition is not None:
        item["edition"] = edition
    if skip:
        item["skip"] = True
    if cloud:
        item["cloud"] = cloud
    ov[rel] = item


# ---------------------------------------------------------------- LHE 期号制
# Issue 260 = 2024-01，之后每期一个月，跨年连续。
def lhe_month(issue: int):
    off = issue - 260
    return 2024 + off // 12, off % 12 + 1


for year in (2024, 2025, 2026):
    d = os.path.join(SRC, "LHE", str(year))
    for f in sorted(os.listdir(d)):
        if not f.lower().endswith(".pdf"):
            continue
        m = (re.search(r"Issue[_ ]?(\d{3})", f)
             or re.search(r"_[IWN][_ ]?(\d{3})[_ ]", f))
        if not m:
            continue
        issue = int(m.group(1))
        # 编号可能落在上一年（如 271 属 2024 年最后���）
        y, mo = lhe_month(issue)
        if y != year:
            continue
        rel = f"LHE/{year}/{f}"
        if issue == 267 and "freemagazines" in f:
            add(rel, skip=True)          # 与 N_267_-_August_2024 同一期
            continue
        add(rel, date=f"{y:04d}-{mo:02d}", key=f"{y:04d}-{mo:02d}-issue-{issue}",
            label=f"{y} 年 {mo} 月 · Issue {issue}",
            cloud=f"外文期刊/月刊/LHE/{y}/LHE{issue}.jpg")

# ---------------------------------------------------------------- SPB 月份制
# Issue 号即月份号：SPB2401 = 2024 年 1 月。
for year in (2024, 2025, 2026):
    d = os.path.join(SRC, "SPB", str(year))
    for f in sorted(os.listdir(d)):
        if not f.lower().endswith(".pdf"):
            continue
        m = re.search(r"Issue_(\d+)_(\d{4})", f) or re.search(r"Spielbox_I(\d+)_(\d{4})", f)
        if m:
            mo = int(m.group(1))
            rel = f"SPB/{year}/{f}"
            add(rel, date=f"{year:04d}-{mo:02d}", key=f"{year:04d}-{mo:02d}",
                label=f"{year} 年 {mo} 月",
                cloud=f"外文期刊/月刊/SPB/{year}/SPB{year % 100:02d}{mo:02d}.jpg")
            continue
        m = re.search(r"-(January|February|March|April|May|June|July|August|September|October|November|December)_(\d{4})", f)
        if m:
            mo = ["January", "February", "March", "April", "May", "June", "July",
                  "August", "September", "October", "November", "December"].index(m.group(1)) + 1
            rel = f"SPB/{year}/{f}"
            add(rel, date=f"{year:04d}-{mo:02d}", key=f"{year:04d}-{mo:02d}",
                label=f"{year} 年 {mo} 月",
                cloud=f"外文期刊/月刊/SPB/{year}/SPB{year % 100:02d}{mo:02d}.jpg")

# ---------------------------------------------------------------- DPD
# 月份制：文件名自带月份与日期；N 系列为同年第 N 期（1=1月 2=2月 3=4月 4=5月
# 5=7月 6=8月 7=9月 8=11月），与封面 “number N” 一致。
DPD_ORDINAL = {1: 1, 2: 2, 3: 4, 4: 5, 5: 7, 6: 8, 7: 9, 8: 11}
DPD_MONTHS = ["January", "February", "March", "April", "May", "June", "July",
              "August", "September", "October", "November", "December"]
for year in (2024, 2025, 2026):
    d = os.path.join(SRC, "DPD", str(year))
    for f in sorted(os.listdir(d)):
        if not f.lower().endswith(".pdf"):
            continue
        rel = f"DPD/{year}/{f}"
        m = re.search(r"_(\d{1,2})_(" + "|".join(DPD_MONTHS) + r")_(\d{4})", f)
        if m:
            day, mon, yy = int(m.group(1)), DPD_MONTHS.index(m.group(2)) + 1, int(m.group(3))
            add(rel, date=f"{yy:04d}-{mon:02d}-{day:02d}", key=f"{yy:04d}-{mon:02d}-{day:02d}",
                label=f"{yy} 年 {mon} 月 {day} 日",
                cloud=f"外文期刊/周刊/DPD/{yy}/DPD{yy % 100:02d}{mon:02d}.jpg")
            continue
        m = re.search(r"(?:_I|_No)(\d)_(\d{4})", f) or re.search(r"_No(\d)_(\d{4})", f)
        if m:
            no, yy = int(m.group(1)), int(m.group(2))
            if (yy, no) in ((2024, 4), (2025, 4)):
                add(rel, skip=True)      # 与同月常规刊重复（封面一致）
                continue
            mo = DPD_ORDINAL[no]
            add(rel, date=f"{yy:04d}-{mo:02d}", key=f"{yy:04d}-{mo:02d}",
                label=f"{yy} 年 {mo} 月 · No.{no}",
                cloud=f"外文期刊/周刊/DPD/{yy}/DPD{yy % 100:02d}N{no:02d}.jpg")

# ---------------------------------------------------------------- CTD / ILE / CRA
CRA_2024 = {"China_Report_ASEAN_08_09_2024_freemagazines_top.pdf": ("2024-08", "2024 年 8 月 – 9 月", "CRA2408.jpg")}
for f, (dt, lb, cn) in CRA_2024.items():
    add(f"CRA/2024/{f}", date=dt, key=dt, label=lb, cloud=f"外文期刊/月刊/CRA/2024/{cn}")

# I Love English Junior：Mai-Juni / July-August 为跨月号，取起始月
add("ILE/2026/I_Love_English_Junior_-_Mai-Juni_2026.pdf",
    date="2026-05", key="2026-05", label="2026 年 5 月 – 6 月",
    cloud="外文期刊/月刊/ILE/2026/ILE2605.jpg")
add("ILE/2026/I_Love_English_Junior_-_July-August_2026.pdf",
    date="2026-07", key="2026-07", label="2026 年 7 月 – 8 月",
    cloud="外文期刊/月刊/ILE/2026/ILE2607.jpg")

# ---------------------------------------------------------------- CRP 数字月份
CRP_MAP = {
    "CRP/2024/China_Report_03_2024.pdf": ("2024-03", "CRP2403.jpg"),
    "CRP/2024/China_Report_05_2024_freemagazines_top.pdf": ("2024-05", "CRP2405.jpg"),
    "CRP/2024/China_Report_06_2024_freemagazines_top.pdf": ("2024-06", "CRP2406.jpg"),
    "CRP/2024/China_Report_07_2024_freemagazines_top.pdf": ("2024-07", "CRP2407.jpg"),
    "CRP/2024/China_Report_09_2024_freemagazines_top.pdf": ("2024-09", "CRP2409.jpg"),
    "CRP/2025/China_Report_02_2025_freemagazines_top.pdf": ("2025-02", "CRP2502.jpg"),
}
for rel, (dt, cn) in CRP_MAP.items():
    y, mo = dt.split("-")
    add(rel, date=dt, key=dt, label=f"{y} 年 {int(mo)} 月",
        cloud=f"外文期刊/周刊/CRP/{y}/{cn}")
add("CRP/2025/China_Report_05_2025_freemagazines_top.pdf", skip=True)  # 与 2025-05 同一期

# ---------------------------------------------------------------- 既有刊物的特殊期次
add("FHM/2021/Sweden/FHM_Sweden_-_February_2021(1).pdf", skip=True)    # 与 2021-02-sweden 同一期
add("FHM/2023/India/FHM_India_-_Volume_14_Issue_9_2023.pdf",
    date="2023-09", key="2023-09-india-issue-9", label="2023 年 9 月 · Issue 9",
    cloud="外文期刊/月刊/FHM/2023/India/FHMIN2309.jpg")

add("FOR/2026/Africa/Forbes_Africa_Dec2025-Jan_2026.pdf", skip=True)   # 已发布为 2026-01-africa

# IOB：Special / Spring 等版本需要与同月常规刊区分
IOB_SPECIAL = [
    ("IOB/2022/IOB_Inside_Out_Babes_-_Spring_Edition_March_2022.pdf", "2022-03-iob-spring", "2022 年 3 月 · Spring Edition", "IOBSP2203.jpg", 2022),
    ("IOB/2023/IOB_Inside_Out_Babes_-_Special_Edition_January_2023.pdf", "2023-01-iob-special", "2023 年 1 月 · Special Edition", "IOBS2301.jpg", 2023),
    ("IOB/2024/IOB_Inside_Out_Babes_Special_Edition_-_November_2024.pdf", "2024-11-iob-special", "2024 年 11 月 · Special Edition", "IOBS2411.jpg", 2024),
    ("IOB/2025/IOB_Inside_Out_Babes_-_Special_Edition_February_2025.pdf", "2025-02-iob-special", "2025 年 2 月 · Special Edition", "IOBS2502.jpg", 2025),
    ("IOB/2025/IOB_Inside_Out_Babes_-_Special_Edition_May_2025.pdf", "2025-05-iob-special", "2025 年 5 月 · Special Edition", "IOBS2505.jpg", 2025),
    ("IOB/2025/IOB_Inside_Out_Babes_-_Special_Edition_June_2025.pdf", "2025-06-iob-special", "2025 年 6 月 · Special Edition", "IOBS2506.jpg", 2025),
    ("IOB/2025/IOB_Inside_Out_Babes_-_Special_Edition_July_2025.pdf", "2025-07-iob-special", "2025 年 7 月 · Special Edition", "IOBS2507.jpg", 2025),
    ("IOB/2025/IOB_Inside_Out_Babes_Special_Edition_-_November_2025.pdf", "2025-11-iob-special", "2025 年 11 月 · Special Edition", "IOBS2511.jpg", 2025),
    ("IOB/2026/IOB_Inside_Out_Babes_-_October_2026_Special_Edition.pdf", "2026-10-iob-special", "2026 年 10 月 · Special Edition", "IOBS2610.jpg", 2026),
]
for rel, key, lb, cn, y in IOB_SPECIAL:
    add(rel, date=key[:7], key=key, label=lb, cloud=f"外文期刊/月刊/IOB/{y}/{cn}")

# LGP：Special 版与同月常规刊区分
LGP_SPECIAL = [
    ("LGP/2021/Lingerie_Plus_Special_-_January_2021.pdf", "2021-01", "LGPS2101.jpg", 2021),
    ("LGP/2021/Lingerie_Plus_Special_-_April_2021.pdf", "2021-04", "LGPS2104.jpg", 2021),
    ("LGP/2021/Lingerie_Plus_Special_-_May_2021.pdf", "2021-05", "LGPS2105.jpg", 2021),
    ("LGP/2021/Lingerie_Plus_Special_-_June_2021.pdf", "2021-06", "LGPS2106.jpg", 2021),
    ("LGP/2023/Lingerie_Plus_Special_Edition_-_October_2023.pdf", "2023-10", "LGPS2310.jpg", 2023),
    ("LGP/2023/Lingerie_Plus_-_Special_December_2023.pdf", "2023-12", "LGPS2312.jpg", 2023),
    ("LGP/2024/Lingerie_Plus_Special_Edition_-_September_2024.pdf", "2024-09", "LGPS2409.jpg", 2024),
    ("LGP/2024/Lingerie_Plus_Special_Edition_-_October_2024.pdf", "2024-10", "LGPS2410.jpg", 2024),
]
for rel, dt, cn, y in LGP_SPECIAL:
    add(rel, date=dt, key=f"{dt}-special", label=f"{dt[:4]} 年 {int(dt[5:7])} 月 · Special",
        cloud=f"外文期刊/月刊/LGP/{y}/{cn}")

# BOU 四季特刊
BOU_SPECIAL = [
    ("BOU/2022/Special/Boudoir_Inspiration_-_Best_of_Black_and_White_2022_Issue.pdf", "2022-12", "2022-12-black-and-white", "2022 年 12 月 · Black and White", 2022, "BOUBX2212.jpg"),
    ("BOU/2024/Special/Boudoir_Inspiration_-_Best_of_Black_and_White_2024_Issue.pdf", "2024-12", "2024-12-black-and-white", "2024 年 12 月 · Black and White", 2024, "BOUBX2412.jpg"),
    ("BOU/2024/Special/Boudoir_Inspiration_-_Best_of_Boudoir_2024_Issue.pdf", "2024-12", "2024-12-best-of-boudoir", "2024 年 12 月 · Best of Boudoir", 2024, "BOUBB2412.jpg"),
    ("BOU/2024/Special/Boudoir_Inspiration_-_Easter_Bunny_2024_Issue.pdf", "2024-03", "2024-03-easter-bunny", "2024 年 3 月 · Easter Bunny", 2024, "BOUEB2403.jpg"),
    ("BOU/2024/Special/Boudoir_Inspiration_-_Valentines_Day_2024_Couples_Boudoir_Issue.pdf", "2024-02", "2024-02-valentines-day-couples", "2024 年 2 月 · Valentine's Day", 2024, "BOUVD2402.jpg"),
]
for rel, dt, key, lb, y, cn in BOU_SPECIAL:
    add(rel, date=dt, key=key, label=lb, cloud=f"外文期刊/月刊/BOU/{y}/Special/{cn}")

# KDY
add("KDY/2022/Kandy_-_11_Year_Anniversary_Issue_2022.pdf",
    date="2022-01", key="2022-01-anniversary", label="2022 年 11 周年特刊",
    cloud="外文期刊/月刊/KDY/2022/KDYAN22.jpg")
add("KDY/2026/Kandy_Magazine_-_15_Year_Anniversary_Issue_2026.pdf",
    date="2026-01", key="2026-01-anniversary", label="2026 年 15 周年特刊",
    cloud="外文期刊/月刊/KDY/2026/KDYAN26.jpg")
add("KDY/2026/Kandy_Magazine_-_Midsummers_2026.pdf",
    date="2026-06", key="2026-06-midsummers", label="2026 年仲夏特刊",
    cloud="外文期刊/月刊/KDY/2026/KDYSU2606.jpg")
add("KDY/2024/Kandy_Magazine_-_September_2024.pdf",
    date="2024-09", key="2024-09-september", label="2024 年 9 月 · September",
    cloud="外文期刊/月刊/KDY/2024/KDY2409.jpg")

# MAX 跨月号
add("MAX/2023/USA/Maxim_USA_-_November-December_2023.pdf",
    date="2023-11", key="2023-11-usa", label="2023 年 11 月 – 12 月",
    cloud="外文期刊/月刊/MAX/2023/USA/MAXUS2311.jpg")
add("MAX/2023/USA/Maxim_USA_-_September-October_2023.pdf",
    date="2023-09", key="2023-09-usa", label="2023 年 9 月 – 10 月",
    cloud="外文期刊/月刊/MAX/2023/USA/MAXUS2309.jpg")

# PLB
add("PLB/2017/Croatia/Playboy_Croatia__Kolovoz_2017.pdf",
    date="2017-08", key="2017-08-croatia", label="2017 年 8 月",
    cloud="外文期刊/月刊/PLB/2017/Croatia/PLBHR1708.jpg")
add("PLB/2017/Germany/Playboy_Germany_Special_Digital_Edition__Jubil_228_ums-Edition_2017.pdf",
    date="2017-12", key="2017-12-germany", label="2017 年 12 月 · Jubiläum 25 周年特刊",
    cloud="外文期刊/月刊/PLB/2017/Germany/PLBDE1712.jpg")

# RDG 跨月号
add("RDG/2025/India/Readers_Digest_India_-_October-November_2025.pdf",
    date="2025-10", key="2025-10-india", label="2025 年 10 月 – 11 月",
    cloud="外文期刊/月刊/RDG/2025/India/RDGIN2510.jpg")

# RIC 期号制
add("RIC/2023/Riche_Magazine_-_Issue_140_Kate_Baker_2023.pdf",
    date="2023-07", key="2023-07-issue-140", label="2023 年 7 月 · Issue 140",
    cloud="外文期刊/月刊/RIC/2023/RIC140.jpg")

# PBS 泳装特刊（页面已存在，用覆盖表钉住避免被判为过期）
add("PBS/2025/Playbabes_Special_Edition_-_Swimsuit_Issue_2025.pdf",
    date="2025-05", key="2025-05-swimsuit", label="2025 年 5 月 · Swimsuit",
    cloud="外文期刊/月刊/PBS/2025/PBSSW2505.jpg")
add("PBS/2026/Playbabes_Special_Edition_-_Swimsuit_2026.pdf",
    date="2026-05", key="2026-05-swimsuit", label="2026 年 5 月 · Swimsuit",
    cloud="外文期刊/月刊/PBS/2026/PBSSW2605.jpg")

# ---------------------------------------------------------------- 写文件
lines = [
    "# ============================================================",
    "# 期次覆盖表 —— 文件名里没有月份、或与既有页面 key 规则不一致的期次",
    "# ============================================================",
    "# 键是相对「原文档」根目录的路径（用 / 分隔）。可用字段：",
    "#   date:    覆盖期次年月（YYYY-MM 或 YYYY-MM-DD）",
    "#   key:     覆盖期次 key（与 content/magazines/<slug>/<key>.md 对应）",
    "#   label:   覆盖期次显示文案",
    "#   edition: 覆盖地区版",
    "#   skip:    true 表示这份 PDF 与已收录期次重复，不再单独建页",
    "#   cloud:   对应的夸克云盘文件（供建分享脚本使用，生成器本身不读）",
    "#",
    "# 由 scripts/build_batch5_overrides.py 生成，改动请同时改脚本。",
    "",
]
for rel, item in ov.items():
    lines.append(f'"{rel}":')
    for k in ("date", "key", "label", "edition", "skip", "cloud"):
        if k in item:
            v = item[k]
            if isinstance(v, bool):
                lines.append(f"  {k}: {str(v).lower()}")
            elif isinstance(v, str):
                lines.append(f'  {k}: "{v}"')
            else:
                lines.append(f"  {k}: {v}")
    lines.append("")
# E 盘偶尔会锁文件，直接写会 PermissionError —— 先写临时文件再原子替换。
def safe_write(path: str, text: str):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


safe_write(OUT, "\n".join(lines))
print(f"覆盖条目 {len(ov)} 条 -> {OUT}")
print("  跳过重复 :", sum(1 for v in ov.values() if v.get("skip")))
print("  新增期次 :", sum(1 for v in ov.values() if not v.get("skip") and v.get("key")))
