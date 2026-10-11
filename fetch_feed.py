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


VERSION_RE = re.compile(r"^\d+(?:\.\d+){2,}$")   # li 的 id，例: 1.60.1.70338
DATE_RE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")
LONG_LIST = 25  # 超过这么多条的列表（主要是物品清单）折叠成一句话


def clean_html(nodes, base: str, link: str) -> str:
    wrapper = BeautifulSoup("<div></div>", "html.parser").div
    for n in nodes:
        wrapper.append(copy.copy(n))
    for img in wrapper.find_all("img"):  # 图标很多，去掉更清爽
        img.decompose()
    for bad in wrapper.find_all(["script", "style", "svg", "button"]):
        bad.decompose()
    for ul in wrapper.find_all(["ul", "ol"]):
        n = len(ul.find_all("li", recursive=False))
        if n > LONG_LIST:
            note = wrapper.new_tag("p")
            a = wrapper.new_tag("a", href=link)
            a.string = f"（共 {n} 项，到网页查看）"
            note.append(a)
            ul.replace_with(note)
    for a in wrapper.find_all("a", href=True):
        a["href"] = urljoin(base, a["href"])
    return wrapper.decode_contents().strip()


def parse(html: str, page_url: str):
    """页面结构: <li id="版本号"> <div>标题区: h2 > time[datetime]</div> <div>正文</div> </li>"""
    soup = BeautifulSoup(html, "html.parser")
    items, seen = [], set()
    for li in soup.find_all("li", id=VERSION_RE):
        h2 = li.find("h2")
        if h2 is None:
            continue
        ver = li["id"]
        if ver in seen:
            continue
        seen.add(ver)

        t = h2.find("time")
        m = DATE_RE.search(t.get("datetime", "")) if t else None
        if m:
            y, mo, d = map(int, m.groups())
        else:  # 退而求其次，从标题文字里取「2026年10月10日」
            m2 = TITLE_RE.search(li.get_text(" ", strip=True)) or re.search(
                r"(\d{4})年(\d{1,2})月(\d{1,2})日", h2.get_text())
            if not m2:
                continue
            y, mo, d = map(int, m2.groups()[:3])

        header = h2
        while header.parent is not li:   # 找到 li 下面直接包着 h2 的那一层
            header = header.parent
        body_nodes = [c for c in li.children if c is not header]
        link = f"{page_url}#{ver}"
        items.append({
            "title": f"{y}年{mo}月{d}日 · 版本 {ver}",
            "link": link,
            "guid": ver,
            "date": datetime(y, mo, d, tzinfo=timezone.utc),
            "html": clean_html(body_nodes, page_url, link),
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


VERSION_RE = re.compile(r"^\d+(?:\.\d+){2,}$")   # li 的 id，例: 1.60.1.70338
DATE_RE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")
LONG_LIST = 25  # 超过这么多条的列表（主要是物品清单）折叠成一句话


def clean_html(nodes, base: str, link: str) -> str:
    wrapper = BeautifulSoup("<div></div>", "html.parser").div
    for n in nodes:
        wrapper.append(copy.copy(n))
    for img in wrapper.find_all("img"):  # 图标很多，去掉更清爽
        img.decompose()
    for bad in wrapper.find_all(["script", "style", "svg", "button"]):
        bad.decompose()
    for ul in wrapper.find_all(["ul", "ol"]):
        n = len(ul.find_all("li", recursive=False))
        if n > LONG_LIST:
            note = wrapper.new_tag("p")
            a = wrapper.new_tag("a", href=link)
            a.string = f"（共 {n} 项，到网页查看）"
            note.append(a)
            ul.replace_with(note)
    for a in wrapper.find_all("a", href=True):
        a["href"] = urljoin(base, a["href"])
    return wrapper.decode_contents().strip()


def parse(html: str, page_url: str):
    """页面结构: <li id="版本号"> <div>标题区: h2 > time[datetime]</div> <div>正文</div> </li>"""
    soup = BeautifulSoup(html, "html.parser")
    items, seen = [], set()
    for li in soup.find_all("li", id=VERSION_RE):
        h2 = li.find("h2")
        if h2 is None:
            continue
        ver = li["id"]
        if ver in seen:
            continue
        seen.add(ver)

        t = h2.find("time")
        m = DATE_RE.search(t.get("datetime", "")) if t else None
        if m:
            y, mo, d = map(int, m.groups())
        else:  # 退而求其次，从标题文字里取「2026年10月10日」
            m2 = TITLE_RE.search(li.get_text(" ", strip=True)) or re.search(
                r"(\d{4})年(\d{1,2})月(\d{1,2})日", h2.get_text())
            if not m2:
                continue
            y, mo, d = map(int, m2.groups()[:3])

        header = h2
        while header.parent is not li:   # 找到 li 下面直接包着 h2 的那一层
            header = header.parent
        body_nodes = [c for c in li.children if c is not header]
        link = f"{page_url}#{ver}"
        items.append({
            "title": f"{y}年{mo}月{d}日 · 版本 {ver}",
            "link": link,
            "guid": ver,
            "date": datetime(y, mo, d, tzinfo=timezone.utc),
            "html": clean_html(body_nodes, page_url, link),
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
