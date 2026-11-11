# -*- coding: utf-8 -*-
"""重建失效的夸克分享链接。

背景：有些分享创建后，云端原文件被删除/重传（fid 变了），分享记录还在但里面是空的，
打开就提示「文件已被分享者删除」。本脚本对这类条目重新创建分享，并写回 KV 数据。

依赖登录态：先用 python scripts/quark_login.py 扫码，生成 scripts/.quark_state.json

用法：
    python scripts/repair_shares.py --dry-run        # 只列出要重建的条目
    python scripts/repair_shares.py                  # 重建并校验，结果写 .repair_result.json
    python scripts/repair_shares.py --apply          # 重建 + 更新 .links_kv.json / .links_bulk.json
"""
from __future__ import annotations

import argparse
import collections
import json
import time
import urllib.parse
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
STATE = HERE / ".quark_state.json"
LINKS = HERE / ".links_kv.json"
SHARES_SNAP = HERE / ".cloud_shares.json"
FILES_SNAP = HERE / ".cloud_files_new.json"
CHECK = HERE / ".share_check.json"
RESULT = HERE / ".repair_result.json"

API = "https://drive-pc.quark.cn/1/clouddrive"
Q = {"pr": "ucpro", "fr": "pc"}
HEAD = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://pan.quark.cn/",
    "Origin": "https://pan.quark.cn",
}


def make_session() -> requests.Session:
    if not STATE.exists():
        raise SystemExit("缺少登录态 .quark_state.json，先运行 python scripts/quark_login.py")
    raw = json.loads(STATE.read_text(encoding="utf-8")).get("cookies", [])
    ck = {c["name"]: c["value"] for c in raw if "quark.cn" in c.get("domain", "")}
    if not ck.get("__puus"):
        raise SystemExit("登录态已失效，重新运行 python scripts/quark_login.py")
    s = requests.Session()
    s.cookies.update(ck)
    s.headers.update(HEAD)
    return s


class Quark:
    def __init__(self) -> None:
        self.s = make_session()
        self._dirs: dict[tuple[str, str], str] = {}

    def _get(self, path: str, **params) -> dict:
        p = dict(Q)
        p.update(params)
        for i in range(4):
            j = self.s.get(f"{API}/{path}", params=p, timeout=30).json()
            if j.get("code") == 0:
                return j
            if j.get("code") in (41029, 429, 31001):
                time.sleep(3 * (i + 1))
                continue
            raise RuntimeError(f"{path} 失败: code={j.get('code')} {j.get('message')}")
        raise RuntimeError(f"{path} 多次被限流")

    def _post(self, path: str, body: dict) -> dict:
        for i in range(4):
            j = self.s.post(f"{API}/{path}", params=Q, json=body, timeout=30).json()
            if j.get("code") == 0:
                return j
            if j.get("code") in (41029, 429, 31001):
                time.sleep(4 * (i + 1))
                continue
            raise RuntimeError(f"{path} 失败: code={j.get('code')} {j.get('message')}")
        raise RuntimeError(f"{path} 多次被限流")

    def ls(self, fid: str) -> list[dict]:
        out, page = [], 1
        while True:
            j = self._get("file/sort", pdir_fid=fid, _page=page, _size=100, _fetch_total=1)
            lst = j["data"]["list"]
            out += lst
            if len(lst) < 100:
                return out
            page += 1

    def child_fid(self, parent: str, name: str) -> str:
        key = (parent, name)
        if key in self._dirs:
            return self._dirs[key]
        hit = [x for x in self.ls(parent) if x["file_name"] == name and x["file_type"] == 0]
        if not hit:
            raise RuntimeError(f"云端找不到目录: {name}（上层 fid={parent}）")
        self._dirs[key] = hit[0]["fid"]
        return self._dirs[key]

    def walk(self, path: str) -> str:
        fid = "0"
        for part in [p for p in path.split("/") if p]:
            fid = self.child_fid(fid, part)
        return fid

    def find_file(self, dir_path: str, name: str) -> str:
        fid = self.walk(dir_path)
        hit = [x for x in self.ls(fid) if x["file_name"] == name and x["file_type"] == 1]
        if not hit:
            raise RuntimeError(f"目录 {dir_path} 里没有 {name}")
        return hit[0]["fid"]

    def share_file(self, fid: str, title: str) -> str:
        """创建分享，返回 share_id（新版接口是异步任务，需轮询 /task）。"""
        j = self._post(
            "share",
            {"fid_list": [fid], "title": title, "url_type": 1, "expired_type": 1},
        )
        tid = (j.get("data") or {}).get("task_id")
        if not tid:
            raise RuntimeError(f"没有拿到 task_id: {j}")
        for i in range(10):
            t = self._get("task", task_id=tid, retry_index=i)
            data = t.get("data") or {}
            if data.get("status") == 2:
                sid = data.get("share_id")
                if not sid:
                    raise RuntimeError(f"任务完成但没有 share_id: {data}")
                return sid
            if data.get("status") == 3:
                raise RuntimeError(f"分享任务失败: {data}")
            time.sleep(1.2)
        raise RuntimeError("分享任务轮询超时")

    def share_index(self) -> dict[str, dict]:
        """把我名下所有分享拉成 share_id -> 记录 的索引。"""
        out: dict[str, dict] = {}
        page = 1
        while True:
            j = self._get(
                "share/mypage/detail",
                _page=page,
                _size=100,
                exclude_fids="",
                status=1,
            )
            lst = (j.get("data") or {}).get("list") or []
            for x in lst:
                out[x["share_id"]] = x
            if len(lst) < 100:
                return out
            page += 1

    def share_file_count(self, pwd_id: str) -> int:
        j = self._post("share/sharepage/token", {"pwd_id": pwd_id, "passcode": ""})
        # stoken 交给 requests 编码一次即可，自己再 quote 会变成非法 token
        st = j["data"]["stoken"]
        g = self._get(
            "share/sharepage/detail", pwd_id=pwd_id, stoken=st, _page=1, _size=20
        )
        return len((g.get("data") or {}).get("list") or [])


def load_inputs() -> list[dict]:
    links = json.loads(LINKS.read_text(encoding="utf-8"))
    bad = json.loads(CHECK.read_text(encoding="utf-8"))["bad"]
    shares = json.loads(SHARES_SNAP.read_text(encoding="utf-8"))
    files = json.loads(FILES_SNAP.read_text(encoding="utf-8"))
    by_pwd = {s["pwd_id"]: s for s in shares}
    by_name: dict[str, list[dict]] = collections.defaultdict(list)
    for f in files:
        by_name[f["name"]].append(f)

    todo = []
    for item in bad:
        key = item["key"]
        pwd_id = links[key]["url"].split("/")[-1]
        rec = by_pwd.get(pwd_id)
        if not rec:
            print(f"  [跳过] {key} 无分享快照")
            continue
        name = rec["title"]
        cands = by_name.get(name) or []
        if not cands:
            print(f"  [跳过] {key} 云端找不到同名文件 {name}")
            continue
        todo.append(
            {
                "key": key,
                "name": name,
                "dir": cands[0]["dir"],
                "old_url": links[key]["url"],
                "pwd": links[key].get("pwd") or "",
            }
        )
    return todo


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true", help="把新链接写回 .links_kv.json 与 .links_bulk.json")
    ap.add_argument("--delay", type=float, default=1.8, help="每次创建分享的间隔秒数")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    todo = load_inputs()
    if args.limit:
        todo = todo[: args.limit]
    print(f"待重建 {len(todo)} 条，涉及 {len({t['dir'] for t in todo})} 个云端目录")
    if args.dry_run:
        for t in todo:
            print(f"  {t['key']:32s} {t['dir']}/{t['name']}")
        return

    q = Quark()
    done, failed = [], []
    for i, t in enumerate(todo, 1):
        try:
            fid = q.find_file(t["dir"], t["name"])
            t["share_id"] = q.share_file(fid, t["name"])
            print(f"  {i}/{len(todo)} 建分享 {t['key']:28s} share_id={t['share_id']}", flush=True)
        except Exception as exc:  # noqa: BLE001
            failed.append({"key": t["key"], "error": str(exc)})
            print(f"  {i}/{len(todo)} FAIL   {t['key']:28s} {exc}", flush=True)
        time.sleep(args.delay)

    if failed:
        print(f"\n先失败的 {len(failed)} 条：", [x["key"] for x in failed][:5])

    print("\n校验分享内容…")
    try:
        idx = q.share_index()
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"拉取分享列表失败：{exc}")
    for i, t in enumerate(todo, 1):
        sid = t.get("share_id")
        if not sid:
            continue
        rec = idx.get(sid)
        if not rec:
            failed.append({"key": t["key"], "error": "分享列表里找不到刚建的分享"})
            print(f"  {i}/{len(todo)} FAIL   {t['key']:28s} 列表中未找到 {sid}")
            continue
        try:
            n = q.share_file_count(rec["pwd_id"])
        except Exception as exc:  # noqa: BLE001
            failed.append({"key": t["key"], "error": f"校验失败 {exc}"})
            continue
        if n <= 0:
            failed.append({"key": t["key"], "error": "分享内文件数为 0"})
            print(f"  {i}/{len(todo)} FAIL   {t['key']:28s} 文件数=0")
            continue
        t["new_url"] = f"https://pan.quark.cn/s/{rec['pwd_id']}"
        t["new_pwd"] = ""
        done.append(t)
        print(f"  {i}/{len(todo)} OK     {t['key']:28s} {t['new_url']} 文件数={n}", flush=True)
        time.sleep(0.4)

    RESULT.write_text(
        json.dumps({"done": done, "failed": failed}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"\n成功 {len(done)}，失败 {len(failed)}，结果写 {RESULT}")

    if args.apply and done:
        links = json.loads(LINKS.read_text(encoding="utf-8"))
        for t in done:
            links[t["key"]] = {"url": t["new_url"], "pwd": t["new_pwd"]}
        LINKS.write_text(json.dumps(links, ensure_ascii=False, indent=1), encoding="utf-8")
        bulk = [
            {"key": "i:" + k, "value": json.dumps(v, ensure_ascii=False)}
            for k, v in links.items()
        ]
        (HERE / ".links_bulk.json").write_text(
            json.dumps(bulk, ensure_ascii=False, indent=0), encoding="utf-8"
        )
        patch = [
            {"key": "i:" + t["key"], "value": json.dumps({"url": t["new_url"], "pwd": t["new_pwd"]}, ensure_ascii=False)}
            for t in done
        ]
        (HERE / ".links_patch.json").write_text(
            json.dumps(patch, ensure_ascii=False, indent=0), encoding="utf-8"
        )
        print(f"已写回 .links_kv.json / .links_bulk.json，增量补丁 .links_patch.json（{len(patch)} 条）")


if __name__ == "__main__":
    main()
