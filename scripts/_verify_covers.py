import json, re
from pathlib import Path
import pymupdf
from PIL import Image
import numpy as np

SRC=Path(r"E:/迅雷下载/英文杂志/原文档")
CONTENT=Path("content/magazines/penthouse")
TH=Path("static/thumbs/magazines/penthouse")

def sig(im):
    im=im.convert("L").resize((64,64), Image.LANCZOS)
    a=np.asarray(im, dtype=np.float32)
    return a

rows=[]
for md in sorted(CONTENT.glob("*.md")):
    if md.name=="_index.md": continue
    fn=re.search(r'file_name:[ ]*"([^"]+)"', md.read_text(encoding="utf-8")).group(1)
    pdf=next((SRC/"PNT").rglob(fn), None)
    cov=TH/md.stem/"cover.webp"
    if pdf is None or not cov.exists():
        rows.append((md.stem, None, None)); continue
    with pymupdf.open(pdf) as doc:
        pg=doc[0]; r=pg.rect
        zoom=min(520/r.width, 730/r.height)
        pix=pg.get_pixmap(matrix=pymupdf.Matrix(zoom,zoom), alpha=False)
        live=Image.frombytes("RGB",(pix.width,pix.height),pix.samples)
    stored=Image.open(cov).convert("RGB")
    d=float(np.abs(sig(live)-sig(stored)).mean())
    rows.append((md.stem, round(d,1), (live.size, stored.size)))

bad=[r for r in rows if r[1] is not None and r[1] > 8]
print("共", len(rows), "期，与 PDF 第 1 页差异过大:", len(bad))
for r in bad:
    print(f"  {r[0]:26s} diff={r[1]:6.1f}  live={r[2][0]} stored={r[2][1]}")
