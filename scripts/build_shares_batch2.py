# -*- coding: utf-8 -*-
"""2026-11-15 批次2：Economist 11-14 / Science 11-12 / Guardian 11-13 图种已上传，建分享并写回。

用法：
    python scripts/build_shares_batch2.py            # 建分享并校验 -> .new_shares_b2.json
    python scripts/build_shares_batch2.py --apply    # 建分享 + 写回 md / .links_kv.json
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# 复用 build_new_shares.py 的全部函数，只替换 MAP 与输出文件
spec = importlib.util.spec_from_file_location("bns", HERE / "build_new_shares.py")
bns = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bns)

bns.OUT = HERE / ".new_shares_b2.json"
bns.MAP = {
    "economist-2026-11-14-usa": ("外文期刊/周刊/ECO/2026/11月", "ECOUS261114.jpg"),
    "science-2026-11-12": ("外文期刊/周刊/SCI/2026/11月", "SCIUS261112.jpg"),
    "guardian-weekly-2026-11-13": ("外文期刊/周刊/GUW/2026/11月", "GUWUK261113.jpg"),
}

if __name__ == "__main__":
    sys.argv = [sys.argv[0]] + [a for a in sys.argv[1:] if a != "--apply-only"]
    bns.main()
