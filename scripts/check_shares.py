#!/usr/bin/env python3
"""批量检测夸克分享链接是否还有效。

用夸克的 sharepage/token 接口判断：能拿到 stoken 就是有效，
返回 41004/41005 之类的就是失效或被删。

用法
  python scripts/check_shares.py --limit 30          # 只查前 30 条
  python scripts/check_shares.py                     # 全量，约 15 分钟
  python scripts/check_shares.py --limit 30 --out scripts/.share_check.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINKS = ROOT / "scripts" / ".links_kv.json"
OUT = ROOT / "scripts" / ".share_check.json"

API = "https://drive-pc.quark.cn/1/clouddrive/share/sharepage/token?pr=ucpro&fr=pc"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def share_id(url: str) -> str:
    return url.rstrip("/").split("/")[-1]


def probe(pwd_id: str, passcode: str = "") -> dict:
    body = json.dumps({"pwd_id": pwd_id, "passcode": passcode}).encode()
    req = urllib.request.Request(
        API,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": UA,
            "Referer": "https://pan.quark.cn/",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:
        try:
            return json.loads(exc.read().decode())
        except Exception:
            return {"status": exc.code, "code": exc.code, "message": str(exc)}
    except Exception as exc:  # 网络异常
        return {"status": -1, "code": -1, "message": str(exc)}


DETAIL = "https://drive-pc.quark.cn/1/clouddrive/share/sharepage/detail"


def detail_count(pwd_id: str, stoken: str) -> tuple[int, str]:
    """返回 (文件数, 第一条文件名)。空列表说明分享指向的文件已被删除。"""
    q = urllib.parse.urlencode(
        {"pr": "ucpro", "fr": "pc", "pwd_id": pwd_id, "stoken": stoken, "_page": 1, "_size": 20}
    )
    req = urllib.request.Request(
        f"{DETAIL}?{q}",
        headers={"User-Agent": UA, "Referer": "https://pan.quark.cn/"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = json.loads(r.read().decode())
    except Exception:
        return (-1, "")
    lst = ((body.get("data") or {}).get("list")) or []
    return (len(lst), lst[0].get("file_name", "") if lst else "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="最多查多少条，0 = 全部")
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--delay", type=float, default=0.8, help="每次请求间隔秒数")
    ap.add_argument("--match", default="", help="只查 key 含该字符串的条目，如 2026")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    data: dict[str, dict] = json.loads(LINKS.read_text(encoding="utf-8"))
    keys = list(data)[args.offset:]
    if args.match:
        keys = [k for k in keys if args.match in k]
    if args.limit:
        keys = keys[: args.limit]

    ok: list[str] = []
    bad: list[dict] = []
    for i, key in enumerate(keys, 1):
        rec = data[key]
        sid = share_id(rec["url"])
        res = probe(sid, rec.get("pwd") or "")
        live = res.get("status") == 200 and res.get("code") == 0
        if live:
            n, name = detail_count(sid, res["data"]["stoken"])
            if n > 0:
                ok.append(key)
            else:
                bad.append(
                    {"key": key, "share_id": sid, "reason": "empty", "detail": f"文件数={n}"}
                )
        else:
            bad.append(
                {
                    "key": key,
                    "share_id": sid,
                    "reason": "dead",
                    "code": res.get("code"),
                    "message": res.get("message"),
                }
            )
        if i % 20 == 0 or i == len(keys):
            print(f"  {i}/{len(keys)}  正常 {len(ok)}  有问题 {len(bad)}", flush=True)
        time.sleep(args.delay)

    print(f"\n合计 {len(keys)} 条：正常 {len(ok)}，有问题 {len(bad)}")
    if bad:
        print("问题样例：")
        for b in bad[:5]:
            print("  ", b)

    Path(args.out).write_text(
        json.dumps({"ok": ok, "bad": bad}, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"明细已写入 {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
