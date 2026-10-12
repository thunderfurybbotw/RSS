#!/usr/bin/env python3
"""wowclassicforever.info（简体中文）的「新闻」和「最新动态」→ RSS。

用法:
    python wcf.py news   --out site/wcf-news
    python wcf.py latest --out site/wcf-latest
"""
import argparse
import copy
import sys
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from common import (absolutize, build_rss, get, parse_iso, read_previous_items,
                    short_hash, site_base, write_item_page, write_text_atomic)

SITE = "https://wowclassicforever.info"
LANG = "zh-hans"
MAX_NEWS = 20
MAX_DAYS = 30
CACHE_MARK = "<!--wcf-v2-->"  # 改这个标记会让所有新闻正文重新抓一次


def article_body(url):
    """单篇新闻的正文：导语 + 各小节 + 来源。去掉面包屑、标题区、导航和「相关攻略」。"""
    soup = BeautifulSoup(get(url), "html.parser")
    main = soup.select_one("main")
    if main is None:
        raise RuntimeError(f"文章页结构变了：{url}")
    parts = []
    lead = main.select_one("header .content-lead")
    if lead:
        parts.append(copy.copy(lead))
    for child in main.find_all(recursive=False):
        if child.name in ("nav", "header"):
            continue
        if child.get("id") == "related":
            continue
        parts.append(copy.copy(child))
    wrapper = BeautifulSoup("<div></div>", "html.parser").div
    for p in parts:
        wrapper.append(p)
    absolutize(wrapper, url)
    return wrapper.decode_contents().strip()


def build_news(out_dir: Path):
    list_url = f"{SITE}/{LANG}/news/"
    soup = BeautifulSoup(get(list_url), "html.parser")
    cards = soup.select("div.guide-cards > div.guide-card")
    prev = read_previous_items(out_dir / "feed.xml")
    items = []
    for card in cards[:MAX_NEWS]:
        a = card.select_one("h3 a[href]")
        t = card.select_one("time[datetime]")
        if not a or not t:
            continue
        url = urljoin(list_url, a["href"])
        guid = f"wcf-news-{a['href'].strip('/').split('/')[-1]}"
        summary = card.select_one("p")
        # 已经抓过的文章直接用上次的正文，只抓新文章（带当前缓存标记的才复用）
        cached = prev.get(guid, "")
        html = cached if cached.startswith(CACHE_MARK) else CACHE_MARK + article_body(url)
        if not html and summary:
            html = str(summary)
        items.append({
            "title": a.get_text(" ", strip=True),
            "link": url, "orig": url, "guid": guid,
            "date": parse_iso(t["datetime"]), "html": html,
        })
    if not items:
        sys.exit("新闻列表一条都没解析到：页面结构可能变了。")
    write_text_atomic(out_dir / "feed.xml", build_rss(
        items, title="WoW Forever 新闻（wowclassicforever.info）", link=list_url,
        description="wowclassicforever.info 的《魔兽世界》：“无限”新闻，非官方 RSS。",
        lang="zh-cn"))
    print(f"新闻：{len(items)} 条，最新 {items[0]['title']}")


def build_latest(out_dir: Path, base: str):
    page_url = f"{SITE}/{LANG}/latest/"
    soup = BeautifulSoup(get(page_url), "html.parser")
    days = soup.select("ol.timeline > li")
    items = []
    for li in days[:MAX_DAYS]:
        t = li.select_one("time[datetime]")
        body = li.select_one(".timeline__body")
        if not t or not body:
            continue
        day = t["datetime"]
        absolutize(body, page_url)
        html = body.decode_contents().strip()
        first = body.find("li") or body
        teaser = first.get_text(" ", strip=True)
        teaser = teaser.split("：")[0] if "：" in teaser[:30] else teaser[:30]
        date = parse_iso(day)
        item = {
            "title": f"{date.year}年{date.month}月{date.day}日 最新动态：{teaser}",
            # 当天内容有增改时 guid 会变，阅读器会把它当新文章再推送一次
            "guid": f"wcf-latest-{day}-{short_hash(html)}",
            "date": date,
            "orig": f"{page_url}#{li.get('id', 'day-' + day)}",
            "html": html,
        }
        item["link"] = (write_item_page(out_dir, base, "wcf-latest", day, item, "zh-Hans",
                                        "在 wowclassicforever.info 上查看")
                        if base else item["orig"])
        items.append(item)
    if not items:
        sys.exit("最新动态一条都没解析到：页面结构可能变了。")
    write_text_atomic(out_dir / "feed.xml", build_rss(
        items, title="WoW Forever 最新动态（wowclassicforever.info）", link=page_url,
        description="wowclassicforever.info 每天的更新记录，非官方 RSS。", lang="zh-cn"))
    print(f"最新动态：{len(items)} 天，最新 {items[0]['title']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["news", "latest"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--base-url")
    args = ap.parse_args()
    out_dir = Path(args.out)
    if args.kind == "news":
        build_news(out_dir)
    else:
        build_latest(out_dir, site_base(args.base_url))


if __name__ == "__main__":
    main()
