#!/usr/bin/env python3
"""删除期次 md 里与详情页参数表重复的「## 本期信息」正文块。

详情页模板已经把刊物、期次、页数、文件大小、分类、年份、入库日期渲染成
参数表（.mg-facts），md 里的这份列表是同一份信息的第二次展示，去掉即可。
只处理正文以「## 本期信息」开头的期次文件；其它自定义正文一律保留。

幂等，可反复运行。默认只预览，加 --apply 才写文件。
读写都用 newline=''，保持原有 CRLF/LF 行尾不变，避免整篇 diff。
"""
from pathlib import Path
import argparse
import re

ROOT = Path(__file__).resolve().parents[1] / "content" / "magazines"
# 开头 front matter（含结尾的 --- 与换行）+ 其余正文
FM = re.compile(r"(?s)^(\ufeff?---\r?\n.*?\r?\n---\r?\n)(.*)$")


def read(p: Path) -> str:
    with p.open("r", encoding="utf-8", newline="") as f:
        return f.read()


def write(p: Path, s: str) -> None:
    with p.open("w", encoding="utf-8", newline="") as f:
        f.write(s)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真正写文件；默认只预览")
    args = ap.parse_args()

    changed = empty = kept = broken = 0
    for p in sorted(ROOT.glob("*/*.md")):
        if p.name == "_index.md":
            continue
        s = read(p)
        m = FM.match(s)
        if not m:
            broken += 1
            print("无法解析 front matter，跳过:", p)
            continue
        front, body = m.group(1), m.group(2)
        if not body.strip():
            empty += 1
            continue
        if not body.lstrip().startswith("## 本期信息"):
            kept += 1
            print("保留非「本期信息」正文:", p, repr(body[:80]))
            continue
        changed += 1
        if args.apply:
            write(p, front)

    print(f"待清理 {changed} 个，已是空正文 {empty} 个，"
          f"保留其它正文 {kept} 个，解析失败 {broken} 个")
    if not args.apply:
        print("（预览模式，未写文件；确认后加 --apply）")


if __name__ == "__main__":
    main()
