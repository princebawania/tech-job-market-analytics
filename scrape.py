"""
Scrape HackerNews "Ask HN: Who is hiring?" monthly threads into raw job postings.

Each month, HN user `whoishiring` posts a "Who is hiring?" thread; every top-level
comment in it is one job posting. We use the public HN Algolia API (no key, no
anti-bot) to (1) find the monthly threads and (2) pull their top-level comments.

Output: one CSV row per job posting.

Usage:
    python scrape.py --months 24 --out data/raw/postings.csv
    python scrape.py --months 6                 # quick test run
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import re
import time
import urllib.request
from datetime import datetime, timezone

ALGOLIA = "https://hn.algolia.com/api/v1"
UA = {"User-Agent": "jobmarket-research/1.0 (student analytics project)"}


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def _get(url: str, retries: int = 4, timeout: int = 30) -> dict:
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except Exception as e:                       # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"GET failed after {retries} tries: {url}\n{last}")


# --------------------------------------------------------------------------- #
# text cleaning
# --------------------------------------------------------------------------- #
_TAG = re.compile(r"<[^>]+>")


def clean_html(text: str) -> str:
    if not text:
        return ""
    t = text.replace("<p>", "\n").replace("</p>", "\n")
    t = _TAG.sub(" ", t)
    t = html.unescape(t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t.strip()


def month_of(created_at_i: int) -> str:
    return datetime.fromtimestamp(created_at_i, tz=timezone.utc).strftime("%Y-%m")


# --------------------------------------------------------------------------- #
# discovery + fetch
# --------------------------------------------------------------------------- #
def find_hiring_threads(max_threads: int, sleep: float = 0.5) -> list[dict]:
    """Return the most recent 'Who is hiring?' story threads (id, month)."""
    threads, page = [], 0
    while len(threads) < max_threads * 2 and page < 20:
        url = (f"{ALGOLIA}/search_by_date?tags=story,author_whoishiring"
               f"&hitsPerPage=50&page={page}")
        data = _get(url)
        hits = data.get("hits", [])
        if not hits:
            break
        for h in hits:
            title = (h.get("title") or "").lower()
            if "who is hiring" in title:
                threads.append({
                    "story_id": str(h["objectID"]),
                    "title": h.get("title"),
                    "created_at_i": h.get("created_at_i"),
                    "month": month_of(h.get("created_at_i")),
                })
        page += 1
        if page >= data.get("nbPages", 0):
            break
        time.sleep(sleep)
    threads.sort(key=lambda t: t["created_at_i"], reverse=True)
    return threads[:max_threads]


def fetch_job_posts(story_id: str, sleep: float = 0.5) -> list[dict]:
    """Top-level comments of a thread == individual job postings."""
    posts, page = [], 0
    while page < 50:
        url = (f"{ALGOLIA}/search?tags=comment,story_{story_id}"
               f"&hitsPerPage=1000&page={page}")
        data = _get(url)
        hits = data.get("hits", [])
        if not hits:
            break
        for h in hits:
            # keep only TOP-LEVEL comments (direct children of the story = job posts)
            if str(h.get("parent_id")) == str(story_id):
                posts.append(h)
        page += 1
        if page >= data.get("nbPages", 1):
            break
        time.sleep(sleep)
    return posts


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=24,
                    help="how many recent monthly threads to scrape")
    ap.add_argument("--out", default="data/raw/postings.csv")
    ap.add_argument("--sleep", type=float, default=0.5, help="politeness delay (s)")
    args = ap.parse_args()

    import os
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)

    print(f"Finding the {args.months} most recent 'Who is hiring?' threads ...")
    threads = find_hiring_threads(args.months, args.sleep)
    print(f"  found {len(threads)} threads: {threads[0]['month']} .. {threads[-1]['month']}"
          if threads else "  none found")

    seen, rows = set(), []
    for t in threads:
        posts = fetch_job_posts(t["story_id"], args.sleep)
        n = 0
        for p in posts:
            pid = str(p["objectID"])
            if pid in seen:
                continue
            seen.add(pid)
            raw = p.get("comment_text") or ""
            rows.append({
                "posting_id": pid,
                "story_id": t["story_id"],
                "thread_month": t["month"],
                "created_at": p.get("created_at"),
                "author": p.get("author"),
                "text_clean": clean_html(raw),
                "text_raw": raw,
            })
            n += 1
        print(f"  {t['month']}: {n} job posts")
        time.sleep(args.sleep)

    cols = ["posting_id", "story_id", "thread_month", "created_at",
            "author", "text_clean", "text_raw"]
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    print(f"\nSaved {len(rows)} job postings from {len(threads)} threads -> {args.out}")


if __name__ == "__main__":
    main()
