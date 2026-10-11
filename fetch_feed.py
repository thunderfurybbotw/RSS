#!/usr/bin/env python3
"""把 ForeverChanges 的「更新檔說明 / 更新档说明」页转成 RSS 2.0。

用法:
    python fetch_feed.py                      # 抓取线上页面，输出 public/feed.xml
    python fetch_feed.py --lang zh-cn         # 简体版
    python fetch_feed.py --file page.html     # 用本地 HTML 测试
"""
import argparse
import copy
import re
import sys
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin
from xml.sax.saxutils import escape

import requests
from bs4 import BeautifulSoup, Tag

SITE = "https://foreverchanges.pro"
UA = "Mozilla/5.0 (personal RSS bridge; checks a few times a day)"
# 例: 「2026年10月10日版本 1.60.1.70338目前版本」
TITLE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日\s*版本\s*(\d+(?:\.\d+)+)")
MAX_ITEMS = 30


def fetch(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    return r.text


def entry_nodes(h2: Tag):
    """返回某条更新的正文节点：优先取 h2 所在的 <li>，否则取到下一个更新 h2 为止的兄弟节点。"""
    li = h2.find_parent("li")
    if li is not None:
        return [c for c in li.children if c is not h2]
    nodes = []
    for sib in h2.next_siblings:
        if isinstance(sib, Tag) and sib.name == "h2":
            break
        nodes.append(sib)
    return nodes


def clean_html(nodes, base: str) -> str:
    wrapper = BeautifulSoup("<div></div>", "html.parser").div
    for n in nodes:
        wrapper.append(copy.copy(n))
    for img in wrapper.find_all("img"):  # 图标很多，去掉更清爽
        img.decompose()
    for bad in wrapper.find_all(["script", "style", "svg"]):
        bad.decompose()
    for a in wrapper.find_all("a", href=True):
        a["href"] = urljoin(base, a["href"])
    return wrapper.decode_contents().strip()


def parse(html: str, page_url: str):
    soup = BeautifulSoup(html, "html.parser")
    items, seen = [], set()
    for h2 in soup.find_all("h2"):
        text = h2.get_text(" ", strip=True)
        m = TITLE_RE.search(text)
        if not m:
            continue
        y, mo, d, ver = m.groups()
        if ver in seen:
            continue
        seen.add(ver)
        body = clean_html(entry_nodes(h2), page_url)
        items.append({
            "title": f"{y}年{int(mo)}月{int(d)}日 · 版本 {ver}",
            "link": f"{page_url}#{ver}",
            "guid": ver,
            "date": datetime(int(y), int(mo), int(d), tzinfo=timezone.utc),
            "html": body,
        })
        if len(items) >= MAX_ITEMS:
            break
    return items


def build_rss(items, page_url: str, lang: str) -> str:
    now = format_datetime(datetime.now(timezone.utc))
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0"><channel>',
        "<title>WoW Forever 更新档说明 (ForeverChanges)</title>",
        f"<link>{escape(page_url)}</link>",
        "<description>ForeverChanges.pro 的 Beta 更新档说明，非官方 RSS。</description>",
        f"<language>{lang}</language>",
        f"<lastBuildDate>{now}</lastBuildDate>",
    ]
    for it in items:
        out += [
            "<item>",
            f"<title>{escape(it['title'])}</title>",
            f"<link>{escape(it['link'])}</link>",
            f'<guid isPermaLink="false">foreverchanges-{escape(it["guid"])}</guid>',
            f"<pubDate>{format_datetime(it['date'])}</pubDate>",
            "<description><![CDATA[" + it["html"].replace("]]>", "]]]]><![CDATA[>") + "]]></description>",
            "</item>",
        ]
    out.append("</channel></rss>")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="zh-tw", choices=["zh-tw", "zh-cn"])
    ap.add_argument("--file", help="读取本地 HTML（测试用）")
    ap.add_argument("--out", default="public/feed.xml")
    args = ap.parse_args()

    page_url = f"{SITE}/{args.lang}/patch-notes"
    html = Path(args.file).read_text(encoding="utf-8") if args.file else fetch(page_url)
    items = parse(html, page_url)
    if not items:
        # 页面结构变了就报错，避免把空 feed 发布出去覆盖旧的
        sys.exit("没有解析到任何更新条目：页面结构可能变了，请检查 TITLE_RE。")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_rss(items, page_url, args.lang), encoding="utf-8")
    print(f"写入 {out}：{len(items)} 条，最新 {items[0]['title']}")


if __name__ == "__main__":
    main()
