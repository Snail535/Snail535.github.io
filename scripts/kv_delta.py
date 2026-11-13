"""把 .links_kv.json 里 KV 还没写过的条目增量写入（省每日 1000 写配额）"""
import json
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOKEN = (HERE / ".cf_token").read_text().strip()
ACCT = "f5309cc14e54f70864c5b1405751ddb8"
NS = "26591befb8e2488f8fb68a19cf8a4239"
BASE = f"https://api.cloudflare.com/client/v4/accounts/{ACCT}/storage/kv/namespaces/{NS}"


def api(path, payload=None, method=None):
    if method is None:
        method = "PUT" if payload is not None else "GET"
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def existing_keys():
    keys, cur = set(), None
    while True:
        q = "/keys?prefix=i%3A&limit=1000" + (f"&cursor={cur}" if cur else "")
        j = api(q)
        if not j.get("success"):
            sys.exit(f"列 key 失败：{j.get('errors')}")
        batch = j["result"]
        keys |= {k["name"] for k in batch}
        cur = (j.get("result_info") or {}).get("cursor")
        if not cur or not batch:
            return keys


def main():
    apply = "--apply" in sys.argv
    links = json.loads((HERE / ".links_kv.json").read_text(encoding="utf-8"))
    have = existing_keys()
    print(f"KV 现有 {len(have)} 条，本地 {len(links)} 条")
    patch = [{"key": "i:" + k, "value": json.dumps(v, ensure_ascii=False)}
             for k, v in links.items() if "i:" + k not in have]
    print(f"待补 {len(patch)} 条")
    for p in patch[:5]:
        print("  ", p["key"])
    (HERE / ".links_delta.json").write_text(json.dumps(patch, ensure_ascii=False, indent=0),
                                            encoding="utf-8")
    if not apply or not patch:
        return
    for i in range(0, len(patch), 500):
        chunk = patch[i:i + 500]
        j = api("/bulk", chunk, "PUT")
        print(f"  写入 {i + len(chunk)}/{len(patch)} → {j.get('success')}")
        if not j.get("success"):
            print(j.get("errors"))


if __name__ == "__main__":
    main()
