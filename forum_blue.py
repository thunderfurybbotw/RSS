#!/usr/bin/env python3
"""暴雪官方论坛（美服）《魔兽世界：永恒》分区的蓝帖 → RSS。

只收标题前带暴雪图标的回复，也就是暴雪员工的回复；社区志愿者 MVP 的回复不收。
一条蓝帖就是一条 RSS。蓝帖被修改后（版本号变了）会作为新文章再推送一次。

用法:
    python forum_blue.py --out site/blue
"""
import argparse
import sys
from pathlib import Path

from bs4 import BeautifulSoup

from common import (absolutize, build_rss, get, parse_iso, site_base,
                    write_item_page, write_text_atomic)

FORUM = "https://us.forums.blizzard.com"
BASE = f"{FORUM}/en/wow"
CATEGORIES = [
    ("wow-forever/world-of-warcraft-forever-general-discussion", 347),
    ("in-development/wow-forever-beta-discussion", 349),
]
PAGES_PER_CATEGORY = 3     # 每页 30 个帖子，按最近活动排序
NOT_BLUE = {"cs-mvp"}      # MVP 的图标不是暴雪图标
MAX_ITEMS = 60
FEED_DIR = "blue"


def blue_topics():
    seen = {}
    for path, cid in CATEGORIES:
        for page in range(PAGES_PER_CATEGORY):
            data = get(f"{BASE}/c/{path}/{cid}.json?page={page}", as_json=True)
            topics = data.get("topic_list", {}).get("topics", [])
            for t in topics:
                ftp = t.get("first_tracked_post")
                if ftp and t["id"] not in seen:
                    seen[t["id"]] = t
            if not data.get("topic_list", {}).get("more_topics_url"):
                break
    return list(seen.values())


def blue_posts(topic):
    tid = topic["id"]
    detail = get(f"{BASE}/t/{tid}.json", as_json=True)
    title = detail.get("title") or topic.get("title", "")
    slug = detail.get("slug") or topic.get("slug", "topic")
    tracked = detail.get("tracked_posts") or []
    if not tracked and detail.get("first_tracked_post"):
        tracked = [detail["first_tracked_post"]]
    out = []
    for tp in tracked:
        if tp.get("group") in NOT_BLUE:
            continue
        n = tp["post_number"]
        chunk = get(f"{BASE}/t/{tid}/{n}.json", as_json=True)
        post = next((p for p in chunk["post_stream"]["posts"] if p["post_number"] == n), None)
        if not post or post.get("hidden") or post.get("deleted_at"):
            continue
        out.append((title, slug, tid, post))
    return out


def to_item(title, slug, tid, post, base, out_dir):
    n, version = post["post_number"], post.get("version", 1) or 1
    edited = version > 1
    date = parse_iso(post["updated_at"] if edited else post["created_at"])
    who = post.get("username", "Blizzard")
    role = post.get("user_title") or ""
    orig = f"{BASE}/t/{slug}/{tid}/{n}"

    body = BeautifulSoup(post.get("cooked", ""), "html.parser")
    absolutize(body, FORUM)
    head = (f'<p class="meta"><b>{who}</b>{"（" + role + "）" if role else ""} '
            f'{"修改了" if edited else "回复于"}第 {n} 楼'
            f'{"（第 " + str(version) + " 版）" if edited else ""}</p>')
    html = head + str(body)

    item = {
        "title": f"[{who}] {title}" + ("（已更新）" if edited else ""),
        "guid": f"blue-{post['id']}-v{version}",
        "date": date,
        "orig": orig,
        "html": html,
    }
    if base:
        item["link"] = write_item_page(out_dir, base, FEED_DIR, f"{post['id']}-v{version}",
                                       item, "en", "在暴雪论坛查看原帖")
    else:
        item["link"] = orig
    return item


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="site/blue")
    ap.add_argument("--base-url")
    args = ap.parse_args()
    out_dir = Path(args.out)
    base = site_base(args.base_url)

    items = []
    for topic in blue_topics():
        for title, slug, tid, post in blue_posts(topic):
            items.append(to_item(title, slug, tid, post, base, out_dir))
    if not items:
        sys.exit("一条蓝帖都没找到：论坛结构可能变了。")
    items.sort(key=lambda it: it["date"], reverse=True)
    items = items[:MAX_ITEMS]

    write_text_atomic(out_dir / "feed.xml", build_rss(
        items, title="WoW Forever 暴雪蓝帖（美服论坛）",
        link=f"{BASE}/c/wow-forever/346",
        description="暴雪官方论坛《魔兽世界：永恒》分区里暴雪员工的回复，非官方 RSS。",
        lang="en"))
    print(f"蓝帖：{len(items)} 条，最新 {items[0]['title']}")


if __name__ == "__main__":
    main()
