# -*- coding: utf-8 -*-
"""网盘分享链接：生成清单 / 批量回写 / 检查缺口。

三种用法：

1) 生成待填清单（451 期，一行一个文件）
       python scripts/fill_downloads.py --template links.csv

2) 把填好的清单写回站点
       python scripts/fill_downloads.py links.csv
       python scripts/fill_downloads.py links.csv --dry     # 只预演

3) 看还差多少期没填
       python scripts/fill_downloads.py --report

清单列（有表头时按列名识别，顺序可乱）：
    key        期次标识，如 playboy/2025-01-africa
    url        分享链接
    pwd        提取码（可空）
    其余列（magazine / issue / file_name）仅作备注，不会被读取

只写刊物级链接时，key 直接填刊物 slug（如 playboy），会写进 data/downloads.yaml。
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
YAML = HERE / "data" / "downloads.yaml"
CONTENT = HERE / "content" / "magazines"

FIELDS = ("key", "magazine", "issue", "file_name", "url", "pwd")
ALIAS = {"key": {"key", "期次", "标识"}, "url": {"url", "链接", "网盘链接"},
         "pwd": {"pwd", "提取码", "pwd码", "密码"},
         "netdisk": {"file_name", "文件名", "网盘文件名"}}


def read_csv(path: Path):
    """返回 [(key, url, pwd)]，支持有表头 / 无表头；兼容 Excel 另存的引号与制表符。"""
    text = path.read_text(encoding="utf-8-sig")
    lines = [l for l in text.splitlines() if l.strip() and not l.startswith("#")]
    if not lines:
        return []
    delim = "\t" if ("\t" in lines[0] and "," not in lines[0]) else ","
    rows = [[c.strip() for c in r]
            for r in csv.reader(io.StringIO("\n".join(lines)), delimiter=delim)]

    first = [c.lower() for c in rows[0]]
    has_header = any(c in ALIAS["key"] or c in ALIAS["url"] for c in first)

    if has_header:
        idx = {"key": 0, "url": 1, "pwd": None, "netdisk": None}
        for n, col in enumerate(first):
            for k, names in ALIAS.items():
                if col in names:
                    idx[k] = n
        data = rows[1:]

        def cell(r, name):
            n = idx[name]
            return r[n] if n is not None and len(r) > n else ""
    else:
        data = rows

        def cell(r, name):
            pos = {"key": 0, "url": 1, "pwd": 2, "netdisk": None}[name]
            if pos is None:
                return ""
            return r[pos] if len(r) > pos else ""

    out = []
    for i, r in enumerate(data, 2 if has_header else 1):
        if len(r) < 2:
            print(f"  [skip] 第 {i} 行格式不对：{r}")
            continue
        key = cell(r, "key")
        if key:
            out.append((key, cell(r, "url"), cell(r, "pwd"), cell(r, "netdisk")))
    return out


def set_magazine(slug: str, url: str, pwd: str, dry: bool) -> bool:
    text = YAML.read_text(encoding="utf-8")
    pat = re.compile(rf"^(\s*{re.escape(slug)}:\s*)\{{[^}}]*\}}\s*$", re.M)
    if not pat.search(text):
        print(f"  [miss] downloads.yaml 里没有刊物 {slug}")
        return False
    new = pat.sub(lambda m: f'{m.group(1)}{{url: "{url}", pwd: "{pwd}"}}', text, count=1)
    if not dry:
        YAML.write_text(new, encoding="utf-8")
    print(f"  [刊] {slug} → {url}")
    return True


def set_issue(key: str, url: str, pwd: str, dry: bool, netdisk: str = "") -> bool:
    slug, _, issue = key.partition("/")
    md = CONTENT / slug / f"{issue}.md"
    if not md.exists():
        print(f"  [miss] 找不到 {slug}/{issue}")
        return False
    text = md.read_text(encoding="utf-8")
    text = re.sub(r'^download_url:.*$', f'download_url: "{url}"', text, count=1, flags=re.M)
    text = re.sub(r'^download_pwd:.*$', f'download_pwd: "{pwd}"', text, count=1, flags=re.M)
    if netdisk:
        line = f'netdisk_file: "{netdisk}"'
        if re.search(r'^netdisk_file:.*$', text, re.M):
            text = re.sub(r'^netdisk_file:.*$', line, text, count=1, flags=re.M)
        elif re.search(r'^download_pwd:.*$', text, re.M):
            text = re.sub(r'^(download_pwd:.*)$', rf'\1\n{line}', text, count=1, flags=re.M)
    if url:
        text = text.replace("\n> 下载地址整理中，可在此行下方补充。\n", "\n")
    if not dry:
        md.write_text(text, encoding="utf-8")
    print(f"  [期] {key} → {url}")
    return True


def index_issues():
    """扫描 content，返回 [(key, magazine, issue_label, file_name, 是否已有链接)]。"""
    out = []
    for md in sorted(CONTENT.glob("*/*.md")):
        if md.name == "_index.md":
            continue
        text = md.read_text(encoding="utf-8")

        def grab(name):
            m = re.search(rf'^{name}:\s*"?(.*?)"?\s*$', text, re.M)
            return m.group(1) if m else ""

        out.append((f"{md.parent.name}/{md.stem}", grab("magazine"),
                    grab("issue_label"), grab("file_name"),
                    bool(grab("download_url"))))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="?", help="填好的清单 CSV")
    ap.add_argument("--template", metavar="OUT", help="生成待填清单到指定文件")
    ap.add_argument("--report", action="store_true", help="统计还缺多少期")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    issues = index_issues()

    if args.template:
        rows = [(k, mag, lab, fn, "", "") for k, mag, lab, fn, _ in issues]
        rows.sort(key=lambda r: (r[1].lower(), r[0]), reverse=False)
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(FIELDS)
        w.writerows(rows)
        Path(args.template).write_text(buf.getvalue(), encoding="utf-8-sig")
        print(f"已生成 {args.template}：{len(rows)} 行，填 url / pwd 两列即可")
        return

    if args.report:
        done = [i for i in issues if i[4]]
        print(f"共 {len(issues)} 期，已有链接 {len(done)} 期，待补 {len(issues) - len(done)} 期")
        miss = [i for i in issues if not i[4]]
        by_mag = {}
        for k, mag, _, _, _ in miss:
            by_mag[mag or k.split("/")[0]] = by_mag.get(mag or k.split("/")[0], 0) + 1
        for mag, n in sorted(by_mag.items(), key=lambda x: -x[1]):
            print(f"  {mag:<22} 缺 {n} 期")
        return

    if not args.csv:
        ap.print_help()
        return

    src = Path(args.csv)
    if not src.exists():
        sys.exit(f"找不到 {src}")

    items = read_csv(src)
    todo = [i for i in items if i[1]]
    print(f"清单 {len(items)} 条，其中有链接 {len(todo)} 条"
          f"{'（预演，不写文件）' if args.dry else ''}\n")

    ok = 0
    for key, url, pwd, netdisk in todo:
        if "/" in key:
            ok += 1 if set_issue(key, url, pwd, args.dry, netdisk) else 0
        else:
            ok += 1 if set_magazine(key, url, pwd, args.dry) else 0
    print(f"\n成功 {ok} / {len(todo)}")

    if not args.dry:
        left = [i for i in index_issues() if not i[4]]
        print(f"站点仍有 {len(left)} 期没有链接")


if __name__ == "__main__":
    main()
