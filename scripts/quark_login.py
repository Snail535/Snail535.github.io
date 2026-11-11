# -*- coding: utf-8 -*-
"""扫码登录夸克网盘，把登录态存到 scripts/.quark_state.json（该文件被 .gitignore 覆盖）。

用法：
    python scripts/quark_login.py            # 弹出浏览器，等待扫码，最多 5 分钟
    python scripts/quark_login.py --timeout 600

登录成功后会打印 cookie 数量并自动关闭浏览器。
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
STATE = HERE / ".quark_state.json"
HOME = "https://pan.quark.cn/"


def logged_in(cookies: dict) -> bool:
    """夸克登录后会种 __pus / __puus 两个会话 cookie。"""
    return bool(cookies.get("__pus")) and bool(cookies.get("__puus"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=int, default=300, help="等待扫码的秒数")
    args = ap.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="msedge",
            headless=False,
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(no_viewport=True)
        page = ctx.new_page()
        for attempt in range(3):
            try:
                page.goto(HOME, timeout=90000, wait_until="domcontentloaded")
                break
            except Exception as exc:  # noqa: BLE001
                print(f"打开页面失败（第 {attempt + 1} 次）：{exc}", flush=True)
                if attempt == 2:
                    browser.close()
                    raise SystemExit(1)
                time.sleep(3)
        try:
            page.bring_to_front()
            page.evaluate("window.focus()")
        except Exception:
            pass
        page.wait_for_timeout(3000)
        try:
            page.screenshot(path=str(HERE / ".qr_check.png"))
        except Exception:
            pass
        print("已打开夸克网盘，请扫码登录…", flush=True)

        deadline = time.time() + args.timeout
        while time.time() < deadline:
            cookies = {c["name"]: c["value"] for c in ctx.cookies()}
            if logged_in(cookies):
                # 二次确认：真的能调通云盘接口
                try:
                    code = page.evaluate(
                        """async () => {
                            const r = await fetch(
                              'https://drive-pc.quark.cn/1/clouddrive/file/sort?pr=ucpro&fr=pc&pdir_fid=0&_page=1&_size=1',
                              {credentials: 'include'});
                            const j = await r.json();
                            return j.code;
                        }"""
                    )
                except Exception:
                    code = None
                if code == 0:
                    STATE.write_text(
                        json.dumps({"cookies": ctx.cookies()}, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    n = sum(1 for c in ctx.cookies() if "quark.cn" in c.get("domain", ""))
                    print(f"登录成功，已保存 {n} 条夸克 cookie -> {STATE}", flush=True)
                    browser.close()
                    return
            time.sleep(2)

        print("超时未检测到登录，浏览器已关闭。", flush=True)
        browser.close()
        raise SystemExit(1)


if __name__ == "__main__":
    main()
