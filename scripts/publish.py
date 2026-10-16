#!/usr/bin/env python3
"""Publish WalletRisk content: X posts/threads + Telegram channel broadcasts.

Reads the latest generated content from content/daily/<date>/ and posts it.
Requires (user-side, one-time):
  - X:      xurl auth apps add + xurl auth oauth2  (see xurl skill)
  - Telegram: bot token in env, channel chat id in env TG_CHANNEL_ID

Dry-run mode (default) prints exactly what WOULD be posted — safe to run
anytime; nothing is sent without --live.

Usage:
  python3 scripts/publish.py                  # dry-run today's content
  python3 scripts/publish.py --live           # actually post (X + Telegram)
  python3 scripts/publish.py --live --only x
  python3 scripts/publish.py --live --only telegram
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sh(cmd: list[str]) -> tuple[int, str]:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def load_content(day: str | None = None) -> dict | None:
    base = os.path.join(ROOT, "content", "daily")
    day = day or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    p = os.path.join(base, day)
    if not os.path.isdir(p):
        # latest available
        days = sorted(d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))
                      and not d.startswith("week-"))
        if not days:
            return None
        day = days[-1]
        p = os.path.join(base, day)
    out = {"day": day}
    for name in ("x_post.txt", "thread.txt", "telegram.txt", "report.md"):
        fp = os.path.join(p, name)
        out[name] = open(fp).read() if os.path.isfile(fp) else None
    return out


def post_x(content: dict, live: bool, thread: bool = True) -> None:
    post = content.get("x_post.txt")
    if not post:
        print("no x_post.txt found", file=sys.stderr)
        return
    if not live:
        print(f"[dry-run X] would post:\n{post}\n---")
        return
    xurl = os.path.expanduser("~/.local/bin/xurl")
    code, out = sh([xurl, "post", post])
    print(f"xurl post -> rc={code} {out[:200]}")
    if code != 0:
        return
    import json
    try:
        post_id = json.loads(out)["data"]["id"]
        print(f"posted to X: {post_id}")
    except Exception:
        print("posted (could not parse id)")
        return
    if thread and content.get("thread.txt"):
        tweets = [t.strip() for t in content["thread.txt"].split("\n\n") if t.strip()]
        prev = post_id
        for t in tweets[1:]:  # first thread tweet mirrors the post
            code, out = sh([xurl, "reply", prev, t])
            if code == 0:
                try:
                    prev = json.loads(out)["data"]["id"]
                    print(f"thread reply ok: {prev}")
                except Exception:
                    break
            else:
                print(f"thread reply failed: {out[:200]}")
                break


def post_telegram(content: dict, live: bool) -> None:
    msg = content.get("telegram.txt")
    if not msg:
        print("no telegram.txt found", file=sys.stderr)
        return
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TG_CHANNEL_ID")
    if not live:
        print(f"[dry-run TG] would broadcast:\n{msg[:400]}\n---")
        return
    if not token or not chat:
        print("TELEGRAM_BOT_TOKEN / TG_CHANNEL_ID not set — cannot post live.",
              file=sys.stderr)
        return
    import urllib.request
    url = (f"https://api.telegram.org/bot{token}/sendMessage"
           f"?chat_id={chat}&text={urllib.parse.quote(msg[:4000])}")
    with urllib.request.urlopen(url, timeout=30) as r:
        print("telegram:", r.read().decode()[:200])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="actually post")
    ap.add_argument("--only", choices=["x", "telegram"], default=None)
    ap.add_argument("--day", default=None, help="content day (YYYY-MM-DD)")
    args = ap.parse_args()

    content = load_content(args.day)
    if not content:
        print("no content generated yet — run scripts/gen_content.py first",
              file=sys.stderr)
        return 1
    print(f"loaded content for {content['day']}")
    if args.only in (None, "x"):
        post_x(content, args.live)
    if args.only in (None, "telegram"):
        post_telegram(content, args.live)
    return 0


if __name__ == "__main__":
    sys.exit(main())
