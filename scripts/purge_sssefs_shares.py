"""清理上一批误建的 .pdf.sssEFs 分享（已改指图种，无页面引用）。

只用两个条件锁定目标：
1. 标题等于 b81f519 版 md 里的 netdisk_file（那批旧文件名）
2. 今天创建（防止误删同名历史分享）

用法：
  python scripts/purge_sssefs_shares.py --dry-run
  python scripts/purge_sssefs_shares.py --apply
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import repair_shares as rs  # noqa: E402

HERE = Path(__file__).resolve().parent
OLD_NAMES = HERE / ".old_names.json"
DONE_OUT = HERE / ".purged_shares.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--delay", type=float, default=0.4)
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    old = json.loads(OLD_NAMES.read_text(encoding="utf-8"))
    want = {v for v in old.values() if v}
    print("旧文件名 %d 个" % len(want))

    q = rs.Quark()
    idx = q.share_index()
    today = datetime.date.today()
    hits = []
    for r in idx.values():
        title = str(r.get("title", ""))
        if title not in want:
            continue
        d = datetime.datetime.fromtimestamp(r["created_at"] / 1000).date()
        if d != today:
            continue
        hits.append({"share_id": r["share_id"], "pwd_id": r["pwd_id"], "title": title})

    names_hit = {h["title"] for h in hits}
    print("命中分享 %d 个，覆盖旧文件 %d/%d" % (len(hits), len(names_hit), len(want)))
    dup = len(hits) - len(names_hit)
    if dup:
        print("  其中重复创建 %d 个（同一文件多份分享，一并删）" % dup)
    lacking = want - names_hit
    if lacking:
        print("  找不到对应分享 %d 个: %s" % (len(lacking), list(lacking)[:3]))
    print("样例:", [h["title"] for h in hits[:3]])

    if not args.apply:
        DONE_OUT.write_text(json.dumps(hits, ensure_ascii=False, indent=1), encoding="utf-8")
        print("dry-run，未删除；清单已存 %s" % DONE_OUT.name)
        return

    ok, fail = [], []
    for i, h in enumerate(hits, 1):
        try:
            # 注意：接口只认 share_ids；传 pwd_ids 会返回 code 0 但什么都不删
            j = q._post("share/delete", {"share_ids": [h["share_id"]]})
            ok.append(h)
            if i % 20 == 0 or i == len(hits):
                print("  %d/%d 已删" % (i, len(hits)), flush=True)
        except Exception as exc:
            fail.append({**h, "error": str(exc)[:120]})
            print("  FAIL %s %s" % (h["title"], exc), flush=True)
        time.sleep(args.delay)

    print("删除成功 %d，失败 %d" % (len(ok), len(fail)))
    DONE_OUT.write_text(json.dumps({"ok": ok, "failed": fail}, ensure_ascii=False, indent=1),
                        encoding="utf-8")

    # 复核：重新拉一次列表，确认这些 pwd_id 已消失
    left = {r["pwd_id"] for r in q.share_index().values()}
    still = [h for h in ok if h["pwd_id"] in left]
    print("复核：仍存在 %d 个" % len(still))


if __name__ == "__main__":
    main()
