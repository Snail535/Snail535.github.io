#!/usr/bin/env python3
"""去掉期次标签里和「刊物版本」重复的国家/地区后缀。

详情页里「刊物」一行已经由 edition 写成 Playboy（South Africa），
期次再写「2026 年 5 月 · SouthAfrica」就是同一信息第二遍。规范后：

  刊物：Playboy（South Africa）
  期次：2026 年 5 月

只处理 edition 非空、且后缀属于国家/地区别名的情况；
子系列 / 特刊 / 期号后缀（Lingerie Inspiration、Black and White、
IOB、Letters、Issue 147 …）一律保留——它们往往是同月多期的唯一区分。

同时修正同一份 md 的 title / description / cover.alt 里那段后缀，
保证页面 H1、<title>、搜索索引、图片 alt 全部一致。
不动文件名与 key，所以 URL、缩略图路径、网盘匹配都不受影响。

幂等，可反复运行。默认只预览，加 --apply 才写文件。
读写用 newline=''，保持原有 CRLF/LF 行尾。
"""
from pathlib import Path
import argparse
import collections
import re

ROOT = Path(__file__).resolve().parents[1] / "content" / "magazines"
# 字段名 → 该行是否允许替换
FIELDS = ("title", "description", "issue_label", "alt")

# 文件名里出现过的地区型变体（归一化后比较：去空格/标点、转小写）
GEO = {
    "us", "usa", "uk", "nz", "australia", "newzealand",
    "southafrica", "suidafrika", "africa",
    "newzealandnewzealand", "southafricasouthafrica",
}


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower().replace("&", "and"))


def is_geo_dup(variant: str, edition: str) -> bool:
    v, e = norm(variant), norm(edition)
    if not v or not e:
        return False
    if v in GEO:
        return True
    if v == e or (len(v) >= 2 and (e.startswith(v) or v.startswith(e))):
        return True
    return False


def field_of(line: str) -> str:
    m = re.match(r"^(\s*)([a-zA-Z_]+):\s*(.*)$", line)
    return m.group(2) if m else ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    changed, kept = [], collections.Counter()
    for p in sorted(ROOT.glob("*/*.md")):
        if p.name == "_index.md":
            continue
        with p.open("r", encoding="utf-8", newline="") as f:
            lines = f.read().splitlines(keepends=True)

        def get(field: str) -> str:
            for ln in lines:
                if field_of(ln.rstrip("\r\n")) == field:
                    m = re.match(r"^\s*[a-zA-Z_]+:\s*(.*)$", ln.strip())
                    return m.group(1).strip().strip('"') if m else ""
            return ""

        edition = get("edition")
        label = get("issue_label")
        if " · " not in label:
            continue
        base, variant = label.rsplit(" · ", 1)
        if not is_geo_dup(variant, edition):
            kept[variant] += 1
            continue

        suffix = " · " + variant
        new_lines, n = [], 0
        for ln in lines:
            raw = ln.rstrip("\r\n")
            eol = ln[len(raw):]
            if field_of(raw) in FIELDS and suffix in raw:
                raw = raw.replace(suffix, "")
                n += 1
            new_lines.append(raw + eol)

        changed.append((p, variant, n))
        if args.apply:
            with p.open("w", encoding="utf-8", newline="") as f:
                f.writelines(new_lines)

    print(f"待规范 {len(changed)} 个期次；保留非地区型后缀 {sum(kept.values())} 个"
          f"（{len(kept)} 种）")
    print("被去掉的后缀:", collections.Counter(v for _, v, _ in changed).most_common())
    print("保留最多的后缀:", kept.most_common(8))
    if changed:
        print("样例:", changed[0][0], "→ 去掉", repr(changed[0][1]))
    if not args.apply:
        print("（预览模式，未写文件；确认后加 --apply）")


if __name__ == "__main__":
    main()
