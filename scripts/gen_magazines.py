# -*- coding: utf-8 -*-
"""从本地杂志库（PDF）生成 Hugo 内容与缩略图。

数据源：
    E:\\迅雷下载\\英文杂志\\原文档\\<刊物目录>\\<年>\\<月>\\*.pdf
刊物元数据：
    data/magazines.yaml（新增刊物只改这里，或直接放新目录由脚本自动登记）

用法：
    python scripts/gen_magazines.py --scan           # 只盘点，打印清单，不写文件
    python scripts/gen_magazines.py                  # 生成 md + 缩略图（跳过已存在）
    python scripts/gen_magazines.py --no-thumbs      # 只生成 md，不动图片
    python scripts/gen_magazines.py --force          # 覆盖已生成的 md 与图片
    python scripts/gen_magazines.py --only economist,time
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent          # myblog/
REGISTRY = HERE / "data" / "magazines.yaml"
OUT_CONTENT = HERE / "content" / "magazines"
OUT_THUMBS = HERE / "static" / "thumbs" / "magazines"

_CACHE_PATH = HERE / "scripts" / "source_path.txt"


def _source_root() -> Path:
    """杂志库位置：环境变量 MAGAZINE_SRC > scripts/source_path.txt > 默认路径。

    换盘/换机器时只改 source_path.txt（或设环境变量），不用动代码。
    """
    for cand in (os.environ.get("MAGAZINE_SRC", "").strip(),
                 _read_cache()):
        if cand:
            p = Path(cand)
            if p.exists():
                return p
            print(f"[warn] 配置的杂志库不存在：{p}，尝试下一个")
    return Path(r"E:\迅雷下载\英文杂志\原文档")


def _read_cache() -> str:
    """读 source_path.txt 里第一条非注释、非空行。"""
    if not _CACHE_PATH.exists():
        return ""
    for line in _CACHE_PATH.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            return s
    return ""


ROOT_SRC = _source_root()

# 尺寸按「页面展示宽度的 2 倍」定：详情页封面展示 260px、内页预览约 170-190px、
# 列表卡片约 260px。直接渲染到目标尺寸，避免后续二次压缩。
COVER_MAX = (520, 730)
THUMB_MAX = (320, 450)
PREVIEW_MAX = (440, 600)
# WebP 同画质比 JPEG 小 20% 上下；这三个质量档肉眼与原 q84/q76/q80 无差
COVER_Q, THUMB_Q, PREVIEW_Q = 82, 80, 80
IMG_EXT = "webp"

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12, "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
    # 非英语刊名里的月份（德/西），以及少量拼写错误（Ostober）
    "februar": 2, "märz": 3, "mai": 5, "juni": 6, "juli": 7, "oktober": 10,
    "dezember": 12, "ostober": 10,
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9,
    "octubre": 10, "noviembre": 11, "diciembre": 12,
    # 季刊/特刊用词，映射到代表性月份（只影响期次排序与归档，不改变刊名）
    "spring": 3, "summer": 6, "fall": 9, "autumn": 9, "winter": 12,
    "holiday": 12, "holidays": 12, "midsummer": 6, "annual": 12,
}
REGIONS = [
    ("middle east", "Middle East"), ("middleeast", "Middle East"),
    ("usa", "USA"), ("uk", "UK"), ("asia", "Asia"), ("africa", "Africa"),
    ("india", "India"), ("australia", "Australia"), ("europe", "Europe"),
    ("china", "China"), ("japan", "Japan"), ("korea", "Korea"),
]

# ---------------------------------------------------------------- registry
def load_registry():
    """读 data/magazines.yaml。没装 pyyaml 时退化为内置默认值。"""
    try:
        import yaml
    except ImportError:
        print("[warn] 未安装 pyyaml，使用最小内置注册表；建议 pip install pyyaml")
        return {"defaults": {"category": "其他", "language": "English",
                             "adult": False, "cadence": "monthly"},
                "magazines": []}
    with open(REGISTRY, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def build_index(reg):
    """folder -> magazine 映射；同时返回按顺序的刊物列表。"""
    by_folder, mags = {}, []
    for i, m in enumerate(reg.get("magazines") or []):
        item = dict(reg.get("defaults") or {})
        item.update(m)
        item.setdefault("slug", item.get("name", f"mag{i}").lower())
        item["weight"] = item.get("weight", (i + 1) * 10)
        item["folders"] = item.get("folders") or []
        mags.append(item)
        for f in item["folders"]:
            by_folder[f.lower()] = item
    return by_folder, mags


def norm_key(s):
    """目录名归一化：去掉空格/连字符/年份等噪声，只留字母数字。"""
    return re.sub(r"[^a-z0-9]+", "", str(s).lower())


def match_mag(by_folder, folder):
    """先精确匹配，再按前缀匹配。

    这样 `Playboy`、`Playboy 2025`、`Playboy 2026` 会归到同一刊，
    `Pent-house 2018年` 也能命中 `Penthouse`（连字符不影响）。
    """
    low = str(folder).lower()
    if low in by_folder:
        return by_folder[low]
    n = norm_key(folder)
    if not n:
        return None
    best, best_len = None, 0
    for key, mag in by_folder.items():
        kn = norm_key(key)
        if kn and n.startswith(kn) and len(kn) > best_len:
            best, best_len = mag, len(kn)
    return best


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return s or "x"


# ---------------------------------------------------------------- parsing
def tokenize(text: str):
    """切开 下划线/空格/连字符/点，并在字母与数字交界处再切一刀。

    这样 August-September、Dec2025、Aug-Sep 都能拆成独立标记。
    """
    text = re.sub(r"(?<=[A-Za-z])(?=\d)", " ", text)
    text = re.sub(r"(?<=\d)(?=[A-Za-z])", " ", text)
    return [t for t in re.split(r"[\s\-_.,]+", text) if t]


def split_publication_and_date(stem: str):
    """把文件名拆成 (刊物部分, 日期部分)。没有月份则日期部分为空。"""
    tokens = tokenize(stem.replace(".pdf", ""))
    for i, t in enumerate(tokens):
        if t.lower() in MONTHS:
            cut = i
            # 11 April 2026 的日号在月份前，要一起算进日期部分
            if i > 0 and re.fullmatch(r"\d{1,2}", tokens[i - 1]):
                cut = i - 1
            return " ".join(tokens[:cut]).strip(" -_"), " ".join(tokens[cut:])
    return " ".join(tokens), ""


def parse_date_part(part: str):
    """解析日期部分，返回 (start, end, label)。元素为 (y, m, d)，d 可能为 1。"""
    tokens = tokenize(part)
    segs, cur_month, cur_year = [], None, None

    for k, tk in enumerate(tokens):
        low = tk.lower()
        nxt = tokens[k + 1].lower() if k + 1 < len(tokens) else ""
        if low in MONTHS:
            cur_month = MONTHS[low]
            reuse = (segs and segs[-1]["m"] == cur_month
                     and segs[-1]["y"] is None and segs[-1]["d"] is not None)
            if not reuse:
                segs.append({"m": cur_month, "d": None, "y": None})
        elif re.fullmatch(r"(19|20)\d{2}", tk):
            cur_year = int(tk)
            for s in segs:
                if s["y"] is None:
                    s["y"] = cur_year
        elif re.fullmatch(r"\d{1,2}", tk) and 1 <= int(tk) <= 31:
            # 11 April 2026 这种“日在前”的写法；>31 的是期号，交给 variant 处理
            if cur_month is None and nxt in MONTHS:
                segs.append({"m": MONTHS[nxt], "d": int(tk), "y": None})
            elif cur_month:
                if segs and segs[-1]["m"] == cur_month and segs[-1]["d"] is None:
                    segs[-1]["d"] = int(tk)
                elif segs and segs[-1]["m"] == cur_month and segs[-1]["d"] is not None:
                    segs.append({"m": cur_month, "d": int(tk), "y": None})
                elif not segs or segs[-1]["m"] != cur_month:
                    segs.append({"m": cur_month, "d": int(tk), "y": None})

    if not segs:
        return None
    for s in segs:
        s["y"] = s["y"] or cur_year
        s["d"] = s["d"] or 1
    if any(s["y"] is None for s in segs):
        return None

    start = (segs[0]["y"], segs[0]["m"], segs[0]["d"])
    end = (segs[-1]["y"], segs[-1]["m"], segs[-1]["d"])

    def fmt(y, m, d, with_day=True):
        if with_day and d != 1:
            return f"{y} 年 {m} 月 {d} 日"
        return f"{y} 年 {m} 月"

    if len(segs) == 1:
        label = fmt(*start)
    else:
        label = f"{fmt(*start)} – {fmt(*end)}"
    return start, end, label


def _norm(s: str) -> str:
    return re.sub(r"[^a-z]", "", str(s).lower())


# 专题/副刊词里不算“版本名”的噪声词
VARIANT_NOISE = {"issue", "magazine", "edition", "english", "international",
                 "mag", "special", "the"}


def detect_variant(pub_part: str, date_part: str, mag: dict, edition: str) -> str:
    """识别同月多刊的「专题 / 副刊」后缀。

    例：
      Boudoir Inspiration - April 2025 Artistic Nude Issue  -> "Artistic Nude"
      Boudoir Inspiration - April 2025 Lingerie Inspiration Issue
                                                            -> "Lingerie Inspiration"
      Penthouse Letters - April 2019                        -> "Letters"
      Forbes Middle East English Edition - ...              -> ""（纯噪声）
    """
    drop = {_norm(t) for t in tokenize(mag.get("name", ""))}
    drop |= {_norm(t) for t in tokenize(edition)}
    drop.discard("")

    # 「Issue 195」这类期号：必须写进 key，否则同月多期会互撞
    # 只认 1-3 位，避开 "Fall Issue 2024" 这种把年份写进 Issue 的写法
    all_tok = tokenize(pub_part) + tokenize(date_part)
    for i, tk in enumerate(all_tok):
        if (tk.lower() == "issue" and i + 1 < len(all_tok)
                and re.fullmatch(r"\d{1,3}", all_tok[i + 1])):
            return f"Issue {all_tok[i + 1]}"

    words = []
    for tk in tokenize(pub_part):
        if _norm(tk) not in drop:
            words.append(tk)
    for tk in tokenize(date_part):
        low = tk.lower()
        if (low in MONTHS or re.fullmatch(r"(19|20)\d{2}", tk)
                or re.fullmatch(r"\d{1,2}", tk)):
            continue
        words.append(tk)

    words = [w for w in words if w.lower() not in VARIANT_NOISE]
    # 去掉重复词（如 Black White 之类重复出现）
    seen, out = set(), []
    for w in words:
        k = w.lower()
        if k not in seen:
            seen.add(k)
            out.append(w)
    # Black_White_Issue / Black_and_White_Issue 统一成同一写法，避免变两个期次
    low = {w.lower() for w in out}
    if "black" in low and "white" in low:
        return "Black and White"
    return " ".join(out)


def build_editions(reg):
    """国家/地区关键词表，可由 data/magazines.yaml 的 editions: 覆盖扩展。"""
    table = reg.get("editions")
    pairs = list(table.items()) if isinstance(table, dict) else (table or REGIONS)
    return sorted(((str(k), str(v)) for k, v in pairs),
                  key=lambda kv: -len(_norm(kv[0])))


def detect_edition(text: str, editions) -> str:
    """从文件名或目录名里认出国家/地区版本，如 USA、Middle East、India。"""
    if not text:
        return ""
    low = str(text).lower()
    flat = _norm(text)
    for key, name in editions:
        k = _norm(key)
        if not k:
            continue
        if len(k) <= 3:
            # 短键（usa/uk）要求词边界，避免 uk 命中普通单词内部
            if re.search(rf"(?<![a-z]){re.escape(str(key).lower())}(?![a-z])", low):
                return name
        elif k in flat:
            return name
    return ""


# ---------------------------------------------------------------- rendering
def _fitz():
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    return fitz


def render_page(doc, idx, out_path: Path, box, quality):
    from PIL import Image
    fitz = _fitz()
    page = doc[idx]
    r = page.rect
    zoom = min(box[0] / r.width, box[1] / r.height)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.suffix == ".webp":
        img.save(out_path, "WEBP", quality=quality, method=6)
    else:
        img.save(out_path, "JPEG", quality=quality, optimize=True, progressive=True)
    return out_path.stat().st_size


def make_thumbs(pdf: Path, out_dir: Path):
    """封面 + 卡片缩略图 + 4 张内页预览。返回是否成功。"""
    fitz = _fitz()
    try:
        doc = fitz.open(pdf)
        n = doc.page_count
        if n == 0:
            return False
        render_page(doc, 0, out_dir / f"cover.{IMG_EXT}", COVER_MAX, COVER_Q)
        render_page(doc, 0, out_dir / f"thumb.{IMG_EXT}", THUMB_MAX, THUMB_Q)
        picks, seen = [], set()
        for f in (0.18, 0.38, 0.56, 0.74):
            i = min(max(int(n * f), 2), max(n - 3, 1))
            if i not in seen:
                seen.add(i)
                picks.append(i)
        while len(picks) < 4:
            picks.append(min(picks[-1] + 1 if picks else 1, n - 1))
        for k, i in enumerate(picks[:4], start=1):
            render_page(doc, i, out_dir / f"p{k}.{IMG_EXT}", PREVIEW_MAX, PREVIEW_Q)
        doc.close()
        return True
    except Exception as e:  # 个别损坏 PDF 不让整批中断
        print(f"  [ERR] {pdf.name}: {e}")
        return False


# ---------------------------------------------------------------- output
def write_md(rec, mag):
    slug, ed_slug = mag["slug"], rec["edition_slug"]
    rel_img = f"/thumbs/magazines/{slug}/{rec['key']}"
    # SEO：标题带刊名，避免几千个页面都叫「2023 年 1 月」被搜索引擎判为重复低质页。
    # 这段要和 scripts/seo_frontmatter.py 的 make_title / make_description 保持一致。
    seo_name = mag["name"] + (f'（{rec["edition"]} 版）' if rec["edition"] else "")
    seo_title = f'{seo_name} · {rec["label"]}'
    seo_desc = (
        f'{seo_title}，{rec["pages"]} 页。'
        "英文原版杂志在线试读，含封面与内页预览、期次信息与网盘下载入口；"
        "新叶素材杂志库按期更新，可按刊物与年份浏览全部期次。"
    )
    fm = [
        "---",
        f'title: {json.dumps(seo_title, ensure_ascii=False)}',
        f'description: {json.dumps(seo_desc, ensure_ascii=False)}',
        f'date: {rec["date"]}T00:00:00+08:00',
        "draft: false",
        f'magazine: "{mag["name"]}"',
        f'magazine_slug: "{slug}"',
        f'edition: "{rec["edition"]}"',
        f'issue: "{rec["issue"]}"',
        f'issue_label: "{rec["label"]}"',
        f'pages: {rec["pages"]}',
        f'file_size: "{rec["size"]}"',
        f'adult: {"true" if mag.get("adult") else "false"}',
        f'cadence: "{mag.get("cadence", "")}"',
        f'file_name: "{rec["pdf"].name}"',
        f'categories: ["{mag.get("category", "其他")}"]',
        f'years: [{rec["date"][:4]}]',
    ]
    if rec["edition"]:
        fm.append(f'editions: ["{rec["edition"]}"]')
    fm += [
        "cover:",
        f'  image: "{rel_img}/cover.{IMG_EXT}"',
        f'  thumb: "{rel_img}/thumb.{IMG_EXT}"',
        f'  alt: "{mag["name"]}{" " + rec["edition"] if rec["edition"] else ""} {rec["label"]}"',
        # 只有标记为成人内容的刊物才默认遮罩封面
        f'  hidden: {"true" if mag.get("adult") else "false"}',
    ]
    for k in range(1, 5):
        fm.append(f'preview{k}: "{rel_img}/p{k}.{IMG_EXT}"')
    fm += ['download_url: ""', 'download_pwd: ""', "---", ""]
    # 保留已有的下载链接与网盘文件名，重新生成时不清空
    md_path = OUT_CONTENT / slug / f"{rec['key']}.md"
    if md_path.exists():
        old = md_path.read_text(encoding="utf-8")
        for field in ("download_url", "download_pwd", "netdisk_file"):
            m = re.search(rf'^{field}:\s*"?(.*?)"?\s*$', old, re.M)
            if m and m.group(1):
                repl = f'{field}: "{m.group(1)}"'
                fm = [repl if ln.startswith(f"{field}:") else ln for ln in fm]
                if not any(ln.startswith(f"{field}:") for ln in fm):
                    fm.insert(-2, repl)
    # 不再写「## 本期信息」正文：详情页的 .mg-facts 参数表已经展示同样的
    # 刊物/期次/页数/文件/分类，重复输出会让访客看到两遍。只保留 front matter。
    out = OUT_CONTENT / slug / f"{rec['key']}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(fm), encoding="utf-8")
    return out


def write_section_indexes(mags, latest_cover):
    for mag in mags:
        d = OUT_CONTENT / mag["slug"]
        d.mkdir(parents=True, exist_ok=True)
        cover = latest_cover.get(mag["slug"], "")
        lines = [
            "---",
            f'title: "{mag["name"]}"',
            f'weight: {mag["weight"]}',
            f'category: "{mag.get("category", "其他")}"',
            f'cadence: "{mag.get("cadence", "")}"',
            f'color: "{mag.get("color", "#333333")}"',
            f'adult: {"true" if mag.get("adult") else "false"}',
            f'description: "{mag.get("desc", "")}"',
        ]
        if cover:
            lines += ["cover:", f'  thumb: "{cover}"', f'  alt: "{mag["name"]}"']
        lines += ["---", "", mag.get("desc", ""), ""]
        (d / "_index.md").write_text("\n".join(lines), encoding="utf-8")

    root = OUT_CONTENT / "_index.md"
    root.parent.mkdir(parents=True, exist_ok=True)
    root.write_text(
        "---\ntitle: \"杂志库\"\ndescription: \"按期更新的英文原版杂志合集\"\n"
        "---\n\n按刊物浏览，点进任意一期可看封面、内页预览与下载信息。\n",
        encoding="utf-8")


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", action="store_true", help="只盘点不写文件")
    ap.add_argument("--no-thumbs", action="store_true", help="跳过缩略图生成")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的 md 与图片")
    ap.add_argument("--only", default="", help="只处理指定 slug，逗号分隔")
    ap.add_argument("--prune", action="store_true", help="删除刊物目录下已不再生成的旧 md")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    reg = load_registry()
    by_folder, mags = build_index(reg)
    editions = build_editions(reg)

    if not ROOT_SRC.exists():
        sys.exit(f"找不到杂志库目录：{ROOT_SRC}")

    # 自动登记未在 yaml 中出现的目录
    for d in sorted(ROOT_SRC.iterdir()):
        if d.is_dir() and match_mag(by_folder, d.name) is None:
            auto = dict(reg.get("defaults") or {})
            auto.update({"slug": slugify(d.name), "name": d.name, "folders": [d.name],
                         "weight": 900 + len(mags), "color": "#666666",
                         "desc": "（自动登记的刊物，去 data/magazines.yaml 补充分类与简介）"})
            by_folder[d.name.lower()] = auto
            mags.append(auto)
            print(f"[new] 发现未登记目录 {d.name} → 已按「{auto['category']}」临时登记")

    only = {s.strip() for s in args.only.split(",") if s.strip()}
    records, latest_cover = [], {}

    # 预扫描已有缩略图：即使本次 --only 处理部分刊物，
    # 其它刊物的封面索引也不会丢（幂等，可重复跑）
    if OUT_THUMBS.exists():
        for d in OUT_THUMBS.glob("*/*"):
            if (d / f"thumb.{IMG_EXT}").exists():
                slug, key = d.parent.name, d.name
                cur = latest_cover.get(slug)
                if not cur or key > cur[0]:
                    latest_cover[slug] = (
                        key, f"/thumbs/magazines/{slug}/{key}/thumb.{IMG_EXT}")

    for pdf in sorted(ROOT_SRC.rglob("*.pdf")):
        rel = pdf.relative_to(ROOT_SRC)
        folder = rel.parts[0]
        mag = match_mag(by_folder, folder)
        if not mag:
            continue
        if only and mag["slug"] not in only:
            continue

        pub_part, date_part = split_publication_and_date(pdf.stem)
        parsed = parse_date_part(date_part)
        if not parsed:
            print(f"  [skip] 无法解析日期：{rel}")
            continue
        _, end, label = parsed
        y, m, d = end
        edition = detect_edition(pub_part, editions)
        if not edition:
            # 文件名没写国家时，退回到目录名（如 FOR/2026/USA/、ReadersDigest/2025/India/）
            for part in rel.parts[1:-1]:
                edition = detect_edition(part, editions)
                if edition:
                    break
        ed_slug = slugify(edition) if edition else ""
        variant = detect_variant(pub_part, date_part, mag, edition)
        v_slug = slugify(variant) if variant else ""
        issue = f"{y:04d}-{m:02d}" + (f"-{d:02d}" if d != 1 else "")
        key = issue + (f"-{ed_slug}" if ed_slug else "") + (f"-{v_slug}" if v_slug else "")
        if variant:
            label = f"{label} · {variant}"
        if any(r["mag"]["slug"] == mag["slug"] and r["key"] == key for r in records):
            print(f"  [dupe] {rel} 与已收录期次冲突，跳过")
            continue
        date = f"{y:04d}-{m:02d}-{d:02d}"

        records.append({
            "pdf": pdf, "mag": mag, "edition": edition, "edition_slug": ed_slug,
            "issue": issue, "key": key, "date": date, "label": label,
            "pages": 0, "size": f"{pdf.stat().st_size / 1048576:.1f} MB",
        })

    if args.scan:
        by_mag = {}
        for r in records:
            by_mag.setdefault(r["mag"]["slug"], []).append(r)
        print(f"\n共发现 {len(records)} 期，{len(by_mag)} 种刊物：")
        for slug, rs in sorted(by_mag.items()):
            dates = sorted(r["issue"] for r in rs)
            print(f"  {slug:<16} {len(rs):>3} 期   {dates[0]} → {dates[-1]}")
        return

    if not records:
        sys.exit("没有可处理的内容，检查 --only 或目录结构。")

    # 清理命名规则变化后遗留的旧 md（如新增国家后缀导致 key 改变）
    valid = {}
    for r in records:
        valid.setdefault(r["mag"]["slug"], set()).add(f"{r['key']}.md")
    for slug_dir in OUT_CONTENT.iterdir() if OUT_CONTENT.exists() else []:
        if not slug_dir.is_dir():
            continue
        # 只检查本次实际处理到的刊物；否则 --only 会把其它刊的 md 全判成过期
        if slug_dir.name not in valid:
            continue
        stale = [p for p in slug_dir.glob("*.md")
                 if p.name != "_index.md"
                 and p.name not in valid.get(slug_dir.name, set())]
        for p in stale:
            if args.prune:
                p.unlink()
                print(f"  [prune] {slug_dir.name}/{p.name}")
            else:
                print(f"  [stale] {slug_dir.name}/{p.name} 与当前命名不一致，--prune 可清理")

    fitz = _fitz()
    t0 = time.time()
    done = skipped = 0
    OUT_CONTENT.mkdir(parents=True, exist_ok=True)

    for i, rec in enumerate(records, 1):
        mag = rec["mag"]
        md_path = OUT_CONTENT / mag["slug"] / f"{rec['key']}.md"
        thumb_dir = OUT_THUMBS / mag["slug"] / rec["key"]
        exists = md_path.exists() and (thumb_dir / f"cover.{IMG_EXT}").exists()

        if exists and not args.force:
            skipped += 1
        else:
            try:
                with fitz.open(rec["pdf"]) as doc:
                    rec["pages"] = doc.page_count
            except Exception as e:
                print(f"  [ERR] 打不开 {rec['pdf'].name}: {e}")
                continue
            if not args.no_thumbs:
                ok = make_thumbs(rec["pdf"], thumb_dir)
                if not ok:
                    continue
            write_md(rec, mag)
            done += 1

        if not latest_cover.get(mag["slug"]) or rec["issue"] > latest_cover[mag["slug"]][0]:
            if (thumb_dir / f"thumb.{IMG_EXT}").exists():
                latest_cover[mag["slug"]] = (
                    rec["issue"], f"/thumbs/magazines/{mag['slug']}/{rec['key']}/thumb.{IMG_EXT}")

        if i % 10 == 0 or i == len(records):
            print(f"  [{i}/{len(records)}] 生成 {done} 跳过 {skipped}  "
                  f"{time.time() - t0:.0f}s")

    write_section_indexes(mags, {k: v[1] for k, v in latest_cover.items()})
    total = sum(f.stat().st_size for f in OUT_THUMBS.rglob(f"*.{IMG_EXT}")) if OUT_THUMBS.exists() else 0
    print(f"\n完成：生成 {done} 期，跳过 {skipped} 期，耗时 {time.time() - t0:.0f}s")
    print(f"缩略图总量：{total / 1048576:.0f} MB")
    json.dump([{k: str(v) for k, v in r.items()} for r in records],
              open(HERE / ".magazines.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
