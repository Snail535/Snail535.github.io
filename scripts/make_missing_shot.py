"""生成「待补链接」清单图：读 .missing13.json，产出 HTML 再截图成 PNG。"""
import json
import pathlib
import subprocess
import collections

ROOT = pathlib.Path(__file__).resolve().parent
DATA = json.loads((ROOT / ".missing13.json").read_text(encoding="utf-8"))
HTML = ROOT / ".missing13.html"
PNG = ROOT / ".missing13.png"

grouped = collections.OrderedDict()
for item in DATA:
    grouped.setdefault(item["magazine"], []).append(item)

TOTAL = len(DATA)
MAGS = len(grouped)

rows_html = []
for mag, items in grouped.items():
    rows_html.append(
        f'<section class="group"><h2>{mag}<span class="cnt">{len(items)} 期</span></h2>'
    )
    for it in items:
        label = it["issue_label"].replace('"', "")
        meta = f'{it["pages"]} 页 · {it["size"]}'
        u = it["pdf"].upper()
        region = ""
        for pat, tag in (("AUSTRALIA", "AU"), ("_USA", "US"), ("_UK", "UK"),
                         ("ASIA", "ASIA"), ("MIDDLE_EAST", "ME")):
            if pat in u:
                region = tag
                break
        badge = f'<span class="region">{region}</span>' if region else ""
        rows_html.append(
            '<div class="row">'
            f'<div class="issue">{it["issue"]}</div>'
            f'<div class="mid"><div class="label">{badge}{label}</div>'
            f'<div class="file">{it["pdf"]}</div></div>'
            f'<div class="meta">{meta}</div>'
            "</div>"
        )
    rows_html.append("</section>")

html = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 44px 48px 40px; width: 1080px;
    background: #f6f5f2; color: #1c1b19;
    font-family: "Microsoft YaHei", "PingFang SC", system-ui, sans-serif;
    -webkit-font-smoothing: antialiased;
  }}
  header {{ display: flex; align-items: flex-end; justify-content: space-between;
           padding-bottom: 18px; border-bottom: 2px solid #1c1b19; }}
  h1 {{ margin: 0; font-size: 30px; letter-spacing: -.01em; }}
  h1 em {{ font-style: normal; color: #b3261e; }}
  .sub {{ margin: 8px 0 0; font-size: 13.5px; color: #6d6a63; }}
  .stamp {{ font-size: 12.5px; color: #6d6a63; text-align: right; line-height: 1.7; }}
  .stamp b {{ display: block; font-size: 22px; color: #1c1b19; font-weight: 600; }}
  section.group {{ margin-top: 26px; }}
  section.group h2 {{
    display: flex; align-items: baseline; gap: 10px; margin: 0 0 8px;
    padding-left: 10px; border-left: 4px solid #1c1b19;
    font-size: 16.5px; font-weight: 600; letter-spacing: .01em;
  }}
  .cnt {{ font-size: 11.5px; font-weight: 400; color: #8a867e; letter-spacing: .06em; }}
  .row {{
    display: grid; grid-template-columns: 104px 1fr 132px;
    align-items: center; gap: 14px;
    padding: 9px 12px; border-bottom: 1px solid #e3e0d9;
  }}
  section.group .row:last-child {{ border-bottom: 1px solid #d7d3ca; }}
  .issue {{ font: 600 13.5px/1.4 Consolas, "Courier New", monospace; color: #b3261e; }}
  .label {{ font-size: 13.5px; line-height: 1.45; }}
  .region {{
    display: inline-block; margin-right: 7px; padding: 0 5px; border-radius: 3px;
    background: #ece9e2; color: #5d5a53;
    font: 600 10.5px/1.55 Consolas, "Courier New", monospace; letter-spacing: .04em;
  }}
  .file {{
    margin-top: 3px; font: 11.5px/1.4 Consolas, "Courier New", monospace;
    color: #6d6a63; word-break: break-all;
  }}
  .meta {{ font-size: 12px; color: #6d6a63; text-align: right; white-space: nowrap;
           font-variant-numeric: tabular-nums; }}
  footer {{ margin-top: 26px; padding-top: 16px; border-top: 2px solid #1c1b19;
            font-size: 12.5px; color: #4a4741; line-height: 1.85; }}
  footer b {{ color: #1c1b19; }}
  .tag {{ display: inline-block; margin-right: 6px; padding: 1px 7px; border-radius: 3px;
          background: #ebe8e1; font-size: 11.5px; color: #4a4741; }}
</style></head>
<body>
  <header>
    <div>
      <h1>待补网盘链接 <em>{TOTAL}</em> 期</h1>
      <p class="sub">这些期次还没有夸克分享，详情页显示「下载地址整理中」</p>
    </div>
    <div class="stamp"><b>{MAGS} 个刊物</b>整理于 2026-11-12</div>
  </header>
  {''.join(rows_html)}
  <footer>
    <span class="tag">怎么补</span>
    在夸克为每份文件建一个分享 → 复制 <b>pan.quark.cn/s/xxxx</b> 链接 →
    按「刊物 + 期号」回填即可，页面无需重新构建。<br>
    <span class="tag">文件名</span>
    上面灰色等宽字体是本地 PDF 原名，图片名以云盘里的实际文件为准。
  </footer>
</body></html>
"""

HTML.write_text(html, encoding="utf-8")

from playwright.sync_api import sync_playwright  # noqa: E402

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    ctx = b.new_context(viewport={"width": 1080, "height": 900}, device_scale_factor=2)
    pg = ctx.new_page()
    pg.goto(HTML.as_uri(), wait_until="networkidle")
    pg.wait_for_timeout(400)
    pg.screenshot(path=str(PNG), full_page=True)
    b.close()

print("生成:", PNG, PNG.stat().st_size // 1024, "KB")
