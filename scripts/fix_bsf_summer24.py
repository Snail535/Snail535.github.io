# -*- coding: utf-8 -*-
"""11-27：BSF Summer 2024 特刊上架收尾。
- 重建 bbc-science-focus-2024-06 分享 -> BSFSU2406.jpg（Summer 特刊）
- 新建 bbc-science-focus-2024-06-regular 分享 -> BSFUK2406.jpg（June 正刊）
- 写回 .links_kv.json / .links_bulk.json / 两期 md
用法：
    python scripts/fix_bsf_summer24.py --map-only
    python scripts/fix_bsf_summer24.py            # 建分享+校验
    python scripts/fix_bsf_summer24.py --apply-only
"""
import argparse, json, os, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LINKS = HERE / '.links_kv.json'
BULK = HERE / '.links_bulk.json'
OUT = HERE / '.fix_bsf_summer24.json'
MD_SUMMER = ROOT / 'content/magazines/bbc-science-focus/2024-06.md'
MD_REGULAR = ROOT / 'content/magazines/bbc-science-focus/2024-06-regular.md'

# key -> (cloud dir, seed name, md path)
JOBS = {
    'bbc-science-focus-2024-06': ('外文期刊/月刊/BSF/2024', 'BSFSU2406.jpg', MD_SUMMER),
    'bbc-science-focus-2024-06-regular': ('外文期刊/月刊/BSF/2024', 'BSFUK2406.jpg', MD_REGULAR),
}


def safe_write(path, text):
    try:
        path.write_text(text, encoding='utf-8')
    except PermissionError:
        tmp = path.with_name(path.name + '.tmp1127')
        tmp.write_text(text, encoding='utf-8')
        os.replace(tmp, path)


def write_back(done):
    links = json.load(open(LINKS, encoding='utf-8'))
    for it in done:
        links[it['key']] = {'url': it['url'], 'pwd': ''}
        # md 写回 netdisk_file
        md_path = Path(it['md_path'])
        text = md_path.read_text(encoding='utf-8')
        import re
        cloud_name = it['cloud'].rsplit('/', 1)[1]
        if re.search(r'^netdisk_file:', text, re.M):
            text = re.sub(r'^netdisk_file:.*$', f'netdisk_file: "{cloud_name}"', text, count=1, flags=re.M)
        else:
            text = re.sub(r'^(download_pwd:.*)$', lambda m: f'{m.group(1)}\nnetdisk_file: "{cloud_name}"', text, count=1, flags=re.M)
        if 'has_download: true' not in text:
            text = re.sub(r'^(download_pwd:.*)$', r'\1\nhas_download: true', text, count=1, flags=re.M)
        safe_write(md_path, text)
    safe_write(LINKS, json.dumps(links, ensure_ascii=False, indent=1))
    bulk = [{'key': 'i:' + k, 'value': json.dumps(v, ensure_ascii=False)} for k, v in links.items()]
    safe_write(BULK, json.dumps(bulk, ensure_ascii=False, indent=0))
    print(f'[apply] 写回 {len(done)} 条; links 共 {len(links)} 条')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--apply-only', action='store_true')
    ap.add_argument('--map-only', action='store_true')
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    if args.apply_only:
        write_back(json.load(open(OUT, encoding='utf-8'))['done'])
        return

    if args.map_only:
        for k, (d, n, md) in JOBS.items():
            print(k, '->', d + '/' + n, '|', md.name)
        return

    # 云盘树校验
    tree = json.load(open(HERE / '.cloud_tree.json', encoding='utf-8'))
    have = {(r['dir'], r['name']) for r in tree}
    for k, (d, n, md) in JOBS.items():
        print(('OK ' if (d, n) in have else 'MISS '), k, d + '/' + n)

    sys.path.insert(0, str(HERE))
    import repair_shares as rs
    q = rs.Quark()
    try:
        q.s.trust_env = False
    except Exception:
        pass

    done, failed = [], []
    for i, (k, (d, n, md)) in enumerate(JOBS.items(), 1):
        try:
            fid = q.find_file(d, n)
            sid = q.share_file(fid, n)
            print(f'  {i}/2 建分享 {k} -> {sid}', flush=True)
            time.sleep(1.6)
            idx = q.share_index()
            rec = idx.get(sid)
            if not rec:
                raise Exception('列表找不到分享')
            cnt = q.share_file_count(rec['pwd_id'])
            if cnt != 1:
                raise Exception(f'文件数{cnt}')
            done.append({'key': k, 'share_id': sid, 'cloud': f'{d}/{n}',
                         'url': f"https://pan.quark.cn/s/{rec['pwd_id']}", 'md_path': str(md)})
            print(f'  OK {k} {done[-1]["url"]}', flush=True)
        except Exception as e:
            failed.append({'key': k, 'error': str(e)})
            print(f'  FAIL {k} {e}', flush=True)

    safe_write(OUT, json.dumps({'done': done, 'failed': failed}, ensure_ascii=False, indent=1))
    print(f'成功 {len(done)} 失败 {len(failed)} -> {OUT}')
    if args.apply and done:
        write_back(done)


if __name__ == '__main__':
    main()
