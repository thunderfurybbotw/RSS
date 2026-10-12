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
    # 「增強」等标签是带 <title> 的 SVG 图标：保留文字，去掉图形
    for svg in wrapper.find_all("svg"):
        t = svg.find("title")
        label = t.get_text(strip=True) if t else ""
        if label:
            b = wrapper.new_tag("b")
            b.string = label + " "
            svg.replace_with(b)
        else:
            svg.decompose()
    for bad in wrapper.find_all(["script", "style", "button"]):
        bad.decompose()
    # 折叠块展开：很多阅读器不支持 <details>，会显示成收起状态
    for summary in wrapper.find_all("summary"):
        summary.name = "h4"
    for det in wrapper.find_all("details"):
        det.name = "div"
    # 物品清单很长：内容全部保留，但改成「、」分隔的一段链接，阅读起来更紧凑
    for ul in wrapper.find_all(["ul", "ol"]):
        lis = ul.find_all("li", recursive=False)
        item_lis = [li for li in lis if li.find("a", href=re.compile(r"/item/"))]
        # 只压缩物品清单；职业改动列表即使很长也保持一条一行
        if len(lis) > LONG_LIST and len(item_lis) >= len(lis) * 0.8:
            p = wrapper.new_tag("p")
            for i, li in enumerate(lis):
                if i:
                    p.append("、")
                a = li.find("a", href=True)
                name = li.get_text(" ", strip=True)
                if a is not None:
                    new_a = wrapper.new_tag("a", href=a["href"])
                    new_a.string = name
                    p.append(new_a)
                else:
                    p.append(name)
            ul.replace_with(p)
    for a in wrapper.find_all("a", href=True):
        a["href"] = urljoin(base, a["href"])
    return wrapper.decode_contents().strip()


def parse(html: str, page_url: str):
    """页面结构: <li id="版本号"> <div>标题区: h2 > time[datetime]</div> <div>正文</div> </li>"""
    soup = BeautifulSoup(html, "html.parser")
    items, seen = [], set()
    for li in soup.find_all("li"):
        h2 = li.find("h2")
        if h2 is None or h2.find_parent("li") is not li:
            continue
        ver = li.get("id", "")
        if not VERSION_RE.match(ver):
            # 没有版本号的特殊条目（例如 9/12 的 BlizzCon 试玩版），只收标题里带日期的
            if not h2.find("time"):
                continue
            ver = ""
        key = ver or h2.parent.get_text(" ", strip=True)
        if key in seen:
            continue
        seen.add(key)

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
        if ver:
            link, label, guid = f"{page_url}#{ver}", f"版本 {ver}", ver
        else:
            extra = header.get_text(" ", strip=True).replace(h2.get_text(" ", strip=True), "").strip()
            link, label, guid = page_url, extra or "更新", f"{y}-{mo:02d}-{d:02d}"
        items.append({
            "title": f"{y}年{mo}月{d}日 · {label}",
            "link": link,
            "guid": guid,
            "date": datetime(y, mo, d, tzinfo=timezone.utc),
            "html": clean_html(body_nodes, page_url, link),
        })
        if len(items) >= MAX_ITEMS:
            break
    return items


def build_rss(items, page_url: str, lang: str) -> str:
    # 用最新一条的时间：内容没变时文件也不变，不会每次都产生提交
    now = format_datetime(max((it["date"] for it in items), default=datetime.now(timezone.utc)))
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


ITEM_PAGE = """<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta property="og:title" content="{title}">
<meta property="og:type" content="article">
<meta property="article:published_time" content="{iso}">
<link rel="canonical" href="{self_url}">
<style>body{{max-width:720px;margin:2rem auto;padding:0 16px;font:16px/1.7 -apple-system,"PingFang TC","Hiragino Sans",sans-serif;color:#222;background:#fff}}
a{{color:#2563eb}}h1{{font-size:1.5rem;line-height:1.3}}.meta{{color:#666;font-size:.9rem}}
@media (prefers-color-scheme:dark){{body{{color:#ddd;background:#111}}a{{color:#7aa7ff}}.meta{{color:#999}}}}</style>
</head><body><article>
<h1>{title}</h1>
<p class="meta"><time datetime="{iso}">{date}</time> · <a href="{orig}">在 ForeverChanges 上查看原文</a></p>
{body}
</article></body></html>
"""


def site_base(cli_value):
    """GitHub Pages 的网址：优先用参数，其次从 Actions 的环境变量推算。"""
    import os
    if cli_value:
        return cli_value.rstrip("/")
    repo = os.environ.get("GITHUB_REPOSITORY", "")  # 例: thunderfurybbotw/RSS
    if "/" in repo:
        owner, name = repo.split("/", 1)
        if name.lower() == f"{owner.lower()}.github.io":
            return f"https://{owner.lower()}.github.io"
        return f"https://{owner.lower()}.github.io/{name}"
    return ""


def write_item_pages(items, out_dir: Path, base: str, lang: str):
    """每个版本生成一张独立页面，并把 RSS 链接改指向它（阅读器抓全文时只看到这一条）。"""
    item_dir = out_dir / "items"
    item_dir.mkdir(parents=True, exist_ok=True)
    for it in items:
        name = re.sub(r"[^0-9A-Za-z.\-]", "_", it["guid"]) + ".html"
        self_url = f"{base}/items/{name}"
        (item_dir / name).write_text(ITEM_PAGE.format(
            lang=lang,
            title=escape(it["title"]),
            iso=it["date"].strftime("%Y-%m-%d"),
            date=f"{it['date'].year}年{it['date'].month}月{it['date'].day}日",
            self_url=escape(self_url),
            orig=escape(it["link"]),
            body=it["html"],
        ), encoding="utf-8")
        it["link"] = self_url


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="zh-tw", choices=["zh-tw", "zh-cn"])
    ap.add_argument("--file", help="读取本地 HTML（测试用）")
    ap.add_argument("--out", default="public/feed.xml")
    ap.add_argument("--base-url", help="发布网址，例: https://user.github.io/RSS（在 Actions 里会自动推算）")
    args = ap.parse_args()

    page_url = f"{SITE}/{args.lang}/patch-notes"
    html = Path(args.file).read_text(encoding="utf-8") if args.file else fetch(page_url)
    items = parse(html, page_url)
    if not items:
        # 页面结构变了就报错，避免把空 feed 发布出去覆盖旧的
        sys.exit("没有解析到任何更新条目：页面结构可能变了，请检查 TITLE_RE。")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    base = site_base(args.base_url)
    if base:
        write_item_pages(items, out.parent, base, args.lang)
    else:
        print("提示：没有发布网址，链接仍指向原网页（本地测试可加 --base-url）")
    out.write_text(build_rss(items, page_url, args.lang), encoding="utf-8")
    print(f"写入 {out}：{len(items)} 条，最新 {items[0]['title']}")


if __name__ == "__main__":
    main()
