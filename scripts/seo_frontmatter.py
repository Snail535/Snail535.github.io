#!/usr/bin/env python3
"""
批量给 content/magazines/<刊名>/<期次>.md 生成「唯一化」的 title 与 description。

背景：原来 1988 个期次页的 title 都是「2023 年 1 月」这种纯期次，
同一个标题最多重复 22 次，description 又是从正文摘要自动截出来的多行文字。
搜索引擎会把这种大量近重复、正文极短的页面判为低质量页，导致收录率很低。

改成：
  title: "Bossing · 2023 年 1 月"        （HTML <title> 会再拼上「| 新叶素材」）
  description: "Bossing · 2023 年 1 月，82 页。英文原版杂志在线试读，…"

特点：
  * 幂等，可反复运行，不会把刊名越叠越长
  * 只改 front matter 里的 title / description 两行，
    其余字节（含 netdisk_file、download_pwd、链接字段）原样保留，也不动换行风格
  * 不依赖 title 反推刊名，一律从 magazine / edition / issue_label 重新拼

用法：
  python scripts/seo_frontmatter.py            # 预览，只统计不写
  python scripts/seo_frontmatter.py --apply   # 实际写入

注意：scripts/gen_magazines.py 的 write_md 已同步生成同样的两个字段，
以后新增杂志不用再跑本脚本；万一漏跑，补跑一次即可。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content" / "magazines"

KEY_RE = re.compile(r"^([a-z_]+):\s*(.*?)\s*$")


def unquote(v: str) -> str:
    return v.strip().strip('"').strip("'").strip()


def yaml_str(s: str) -> str:
    """用 JSON 的转义规则生成 YAML 双引号字符串，保证中文与特殊字符安全。"""
    return json.dumps(s, ensure_ascii=False)


def make_title(meta: dict) -> str:
    mag = meta.get("magazine", "")
    edition = meta.get("edition", "")
    label = meta.get("issue_label") or meta.get("title") or ""
    name = mag + (f"（{edition} 版）" if edition else "")
    return f"{name} · {label}" if name else label


def make_description(meta: dict, title: str) -> str:
    head = title
    pages = meta.get("pages", "")
    if pages and pages not in ("0", "None"):
        head += f"，{pages} 页"
    return (
        f"{head}。英文原版杂志在线试读，含封面与内页预览、期次信息与网盘下载入口；"
        "新叶素材杂志库按期更新，可按刊物与年份浏览全部期次。"
    )


def line_ending(line: str) -> str:
    return "\r\n" if line.endswith("\r\n") else "\n"


def process(path: Path, apply: bool):
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    if not text.startswith("---"):
        return None
    lines = text.splitlines(keepends=True)

    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None

    fm = lines[1:end]
    meta = {}
    for ln in fm:
        m = KEY_RE.match(ln.rstrip("\r\n"))
        if m:
            meta[m.group(1)] = unquote(m.group(2))

    # 栏目页（_index.md）没有 magazine / issue_label，保持原样
    if not meta.get("magazine") or not meta.get("issue_label"):
        return None

    title = make_title(meta)
    desc = make_description(meta, title)
    if not title:
        return None

    new_fm = []
    has_title = False
    for ln in fm:
        m = re.match(r"^([a-z_]+):", ln)
        key = m.group(1) if m else ""
        if key == "description":
            continue  # 统一插到 title 后面
        if key == "title":
            nl = line_ending(ln)
            new_fm.append(f"title: {yaml_str(title)}{nl}")
            new_fm.append(f"description: {yaml_str(desc)}{nl}")
            has_title = True
        else:
            new_fm.append(ln)
    if not has_title:
        nl = line_ending(lines[0])
        new_fm.insert(0, f"title: {yaml_str(title)}{nl}")
        new_fm.insert(1, f"description: {yaml_str(desc)}{nl}")

    new_text = "".join(lines[:1] + new_fm + lines[end:])
    if new_text == text:
        return (False, title, desc)
    if apply:
        path.write_bytes(new_text.encode("utf-8"))
    return (True, title, desc)


def main():
    apply = "--apply" in sys.argv
    files = sorted(p for p in CONTENT.glob("*/*.md") if p.name != "_index.md")
    changed, skipped, samples, titles = 0, 0, [], []
    for p in files:
        r = process(p, apply)
        if r is None:
            skipped += 1
            continue
        dirty, title, desc = r
        titles.append(title)
        if dirty:
            changed += 1
            if len(samples) < 3:
                samples.append((str(p.relative_to(ROOT)), title, desc))

    print(f"扫描 {len(files)} 个期次页，跳过 {skipped} 个（栏目页或字段缺失）")
    print(f"需要修改 {changed} 个；唯一标题 {len(set(titles))} 个 / 共 {len(titles)} 页")
    for path, title, desc in samples:
        print(f"\n  {path}\n  title: {title}\n  desc : {desc}")
    print("\n" + ("已写入。" if apply else "预览模式，未写入。加 --apply 生效。"))


if __name__ == "__main__":
    main()
