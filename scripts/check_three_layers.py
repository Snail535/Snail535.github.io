# -*- coding: utf-8 -*-
"""三层数量对账：本地 PDF / 图种 jpg / 博客期次 md 必须完全一致。

为什么需要它：2026-11-27 之前统一过一次，但后来又偏了——
  ① PDF 有、md 无：gen_magazines 遇到 [dupe]/[skip] 会静默跳过，没人发现；
  ② 图种目录里混入 _dup_redundant_* 隔离目录，全目录 find 会多算；
  ③ 特刊（Summer/Special）与正刊撞 key，被判 dupe 漏上架。

做法：调用 gen_magazines.py --scan --dump 拿到"按当前规则应该生成的期次清单"，
再和本地 PDF / 图种（排除隔离目录）/ 博客 md / 网盘快照逐一比对。
不一致时打印明细并以 exit(1) 结束，可直接放进收尾清单当闸门。

用法（用哪个解释器跑，内部 scan 就用哪个，需能 import yaml/fitz）：
  PYTHONPATH=D:/py_libs DPY scripts/check_three_layers.py
  PYTHONPATH=D:/py_libs DPY scripts/check_three_layers.py --json   # 机器可读

网盘数字来自 scripts/.cloud_tree.json 快照，可能滞后；先跑
  DPY scripts/scan_cloud_tree.py
刷新再对账。
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BLOG = HERE.parent
SRC = Path(r'E:\迅雷下载\英文杂志\原文档')
SEED = Path(r'E:\迅雷下载\英文杂志\图种版')
CONTENT = BLOG / 'content' / 'magazines'
TREE = HERE / '.cloud_tree.json'
DUMP = BLOG / '.scan_dump.json'   # gen_magazines.py 的 HERE 是 myblog/，dump 写在博客根目录


def relparts_isolated(p: Path, root: Path) -> bool:
    """图种是否位于 _ 开头的隔离目录内。"""
    try:
        rel = p.relative_to(root)
    except ValueError:
        return False
    return any(part.startswith('_') for part in rel.parts[:-1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    errors, warns = [], []

    # ---- 0. 复用 gen_magazines 的解析规则，拿"应生成期次"清单 ----
    if DUMP.exists():
        DUMP.unlink()
    proc = subprocess.run([sys.executable, str(HERE / 'gen_magazines.py'), '--scan', '--dump'],
                          capture_output=True, text=True)
    # E 盘写入可见性偶尔延迟：子进程已打印成功但父进程立刻 stat 还看不到，重试几次
    import time
    for _ in range(6):
        if DUMP.exists():
            try:
                if json.load(open(DUMP, encoding='utf-8')):
                    break
            except Exception:
                pass
        time.sleep(0.5)
    if not DUMP.exists():
        print('[FATAL] gen_magazines --scan --dump 未产出清单：')
        print(proc.stderr[-1000:] or proc.stdout[-1000:])
        return 2
    scan = json.load(open(DUMP, encoding='utf-8'))
    scan_keys = {(x['slug'], x['key']) for x in scan}
    scan_pdfs = {os.path.normpath(x['pdf']) for x in scan}
    dupes = [ln.strip() for ln in proc.stdout.splitlines()
             if '[dupe]' in ln or '[skip]' in ln]

    # ---- 1. 本地 PDF（归档脚本口径）----
    pdfs = {os.path.normpath(str(p)) for p in SRC.rglob('*.pdf')}

    # ---- 2. 图种（排除 _ 隔离目录）----
    all_seeds = [p for p in SEED.rglob('*.jpg')]
    seeds = [p for p in all_seeds if not relparts_isolated(p, SEED)]
    isolated = [p for p in all_seeds if relparts_isolated(p, SEED)]

    # ---- 3. 博客期次 md ----
    mds = [p for p in CONTENT.glob('*/*.md') if p.name != '_index.md']
    md_keys = {(p.parent.name, p.stem) for p in mds}

    # ---- 4. 网盘快照 ----
    cloud = []
    if TREE.exists():
        tree = json.load(open(TREE, encoding='utf-8'))
        cloud = [r for r in tree if r.get('name', '').lower().endswith('.jpg')]
    else:
        warns.append('缺 .cloud_tree.json 快照，网盘数未校验（先跑 scan_cloud_tree.py）')

    counts = {
        '本地PDF': len(pdfs),
        '图种jpg(有效)': len(seeds),
        '网盘jpg(快照)': len(cloud) if cloud else None,
        '应生成期次(scan)': len(scan),
        '博客md': len(mds),
        '隔离图种(不计)': len(isolated),
    }

    # ---- 差异明细 ----
    # a) 有 PDF 但 gen_magazines 没收录（dupe/日期解析失败/未登记刊）
    orphan_pdfs = sorted(pdfs - scan_pdfs)
    # b) scan 有但 md 没生成（生成失败/漏跑）
    missing_md = sorted(scan_keys - md_keys)
    # c) md 有但 scan 没有（旧命名残留，--prune 可清）
    stale_md = sorted(md_keys - scan_keys)
    # d) 数量校验
    for label, a, b in [
        ('PDF vs 图种', len(pdfs), len(seeds)),
        ('PDF vs scan期次', len(pdfs), len(scan)),
        ('scan期次 vs 博客md', len(scan), len(mds)),
        ('图种 vs 网盘', len(seeds), len(cloud) if cloud else len(seeds)),
    ]:
        if a != b:
            errors.append(f'{label} 不等：{a} vs {b}')

    if orphan_pdfs:
        errors.append(f'有 PDF 但 gen_magazines 未收录（{len(orphan_pdfs)} 个，多为 [dupe]/[skip]）：')
        for p in orphan_pdfs[:20]:
            errors.append('   ' + p)
        if len(orphan_pdfs) > 20:
            errors.append(f'   ... 还有 {len(orphan_pdfs)-20} 个')
    if missing_md:
        errors.append(f'应生成但缺 md（{len(missing_md)} 期）：')
        for k in sorted(missing_md)[:20]:
            errors.append(f'   {k[0]}/{k[1]}')
    if stale_md:
        warns.append(f'博客有 md 但 scan 未识别（{len(stale_md)} 期，可能命名规则变更）：')
        for k in sorted(stale_md)[:20]:
            warns.append(f'   {k[0]}/{k[1]}')
    if dupes:
        errors.append(f'gen_magazines 报了 {len(dupes)} 条 [dupe]/[skip]（静默跳过的期次）：')
        for ln in dupes[:20]:
            errors.append('   ' + ln)
    if isolated:
        warns.append(f'图种目录内有 {len(isolated)} 个隔离图种（_ 目录，已正确排除统计）：')
        for p in isolated[:10]:
            warns.append('   ' + str(p))

    # ---- 输出 ----
    if args.json:
        print(json.dumps({
            'ok': not errors,
            'counts': counts,
            'errors': errors,
            'warnings': warns,
            'orphan_pdfs': orphan_pdfs,
            'missing_md': [f'{a}/{b}' for a, b in sorted(missing_md)],
            'stale_md': [f'{a}/{b}' for a, b in sorted(stale_md)],
            'dupes': dupes,
        }, ensure_ascii=False, indent=1))
    else:
        print('=== 三层数量对账 ===')
        for k, v in counts.items():
            print(f'  {k:<18} {v}')
        print()
        if errors:
            print(f'[FAIL] {len(errors)} 处不一致：')
            for e in errors:
                print('  ' + e)
        else:
            print('[OK] 三层数量完全一致，且无重复/漏建期次。')
        if warns:
            print(f'\n[WARN] {len(warns)} 条提示：')
            for w in warns:
                print('  ' + w)

    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
