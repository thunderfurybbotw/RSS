"""各个 feed 脚本共用的工具：抓网页、清理 HTML、生成 RSS 和单独页面。"""
import hashlib
import os
import re
import time
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin
from xml.sax.saxutils import escape

import requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (compatible; personal-rss-bridge/1.0; "
      "+https://github.com/thunderfurybbotw/RSS)")
_session = requests.Session()
_session.headers.update({"User-Agent": UA})


def get(url, *, as_json=False, tries=3, pause=1.0):
    """带重试的 GET。遇到 429/5xx 会等一会儿再试。"""
    last = None
    for i in range(tries):
        try:
            r = _session.get(url, timeout=30)
            if r.status_code in (429, 500, 502, 503, 504):
                last = f"HTTP {r.status_code}"
                time.sleep(pause * (i + 2) * 2)
                continue
            r.raise_for_status()
            time.sleep(pause)  # 对网站客气一点
            if as_json:
                return r.json()
            # 网站没声明字符集时，requests 会按 ISO-8859-1 解码，中文就变乱码；统一按 UTF-8
            if "charset" not in r.headers.get("content-type", "").lower():
                r.encoding = "utf-8"
            return r.text
        except requests.RequestException as e:
            last = str(e)
            time.sleep(pause * (i + 1))
    raise RuntimeError(f"抓取失败 {url}: {last}")


def short_hash(text, n=8):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:n]


def absolutize(soup_or_tag, base):
    for a in soup_or_tag.find_all("a", href=True):
        a["href"] = urljoin(base, a["href"])
    for img in soup_or_tag.find_all("img", src=True):
        img["src"] = urljoin(base, img["src"])
        for attr in ("srcset", "data-src", "loading"):
            img.attrs.pop(attr, None)
    for bad in soup_or_tag.find_all(["script", "style", "button", "form", "noscript"]):
        bad.decompose()
    return soup_or_tag


def site_base(cli_value=None):
    """GitHub Pages 网址：优先用参数，其次从 Actions 的环境变量推算。"""
    if cli_value:
        return cli_value.rstrip("/")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" in repo:
        owner, name = repo.split("/", 1)
        if name.lower() == f"{owner.lower()}.github.io":
            return f"https://{owner.lower()}.github.io"
        return f"https://{owner.lower()}.github.io/{name}"
    return ""


def write_text_atomic(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


ITEM_PAGE = """<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta property="og:title" content="{title}">
<meta property="og:type" content="article">
<meta property="article:published_time" content="{iso}">
<link rel="canonical" href="{self_url}">
<style>body{{max-width:720px;margin:2rem auto;padding:0 16px;font:16px/1.7 -apple-system,"PingFang SC","Hiragino Sans",sans-serif;color:#222;background:#fff}}
a{{color:#2563eb}}h1{{font-size:1.5rem;line-height:1.3}}.meta{{color:#666;font-size:.9rem}}img{{max-width:100%;height:auto}}
blockquote,aside{{border-left:3px solid #ccc;margin:1em 0;padding:0 1em;color:#555}}
@media (prefers-color-scheme:dark){{body{{color:#ddd;background:#111}}a{{color:#7aa7ff}}.meta{{color:#999}}blockquote,aside{{color:#aaa;border-color:#444}}}}</style>
</head><body><article>
<h1>{title}</h1>
<p class="meta"><time datetime="{iso}">{date}</time> · <a href="{orig}">{orig_label}</a></p>
{body}
</article></body></html>
"""


def write_item_page(out_dir: Path, base: str, feed_dir: str, slug: str, item: dict,
                    lang: str, orig_label: str):
    """给一条内容生成独立页面，返回它的网址。"""
    name = re.sub(r"[^0-9A-Za-z.\-]", "_", slug) + ".html"
    self_url = f"{base}/{feed_dir}/items/{name}" if feed_dir else f"{base}/items/{name}"
    d = item["date"]
    write_text_atomic(out_dir / "items" / name, ITEM_PAGE.format(
        lang=lang, title=escape(item["title"]), iso=d.strftime("%Y-%m-%d"),
        date=f"{d.year}年{d.month}月{d.day}日", self_url=escape(self_url),
        orig=escape(item["orig"]), orig_label=escape(orig_label), body=item["html"]))
    return self_url


def build_rss(items, *, title, link, description, lang):
    """生成 RSS。lastBuildDate 用最新一条的时间，内容没变时文件也不变。"""
    newest = max((it["date"] for it in items), default=datetime.now(timezone.utc))
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0"><channel>',
        f"<title>{escape(title)}</title>",
        f"<link>{escape(link)}</link>",
        f"<description>{escape(description)}</description>",
        f"<language>{lang}</language>",
        f"<lastBuildDate>{format_datetime(newest)}</lastBuildDate>",
    ]
    for it in items:
        out += [
            "<item>",
            f"<title>{escape(it['title'])}</title>",
            f"<link>{escape(it['link'])}</link>",
            f'<guid isPermaLink="false">{escape(it["guid"])}</guid>',
            f"<pubDate>{format_datetime(it['date'])}</pubDate>",
            "<description><![CDATA[" + it["html"].replace("]]>", "]]]]><![CDATA[>") + "]]></description>",
            "</item>",
        ]
    out.append("</channel></rss>")
    return "\n".join(out) + "\n"


def read_previous_items(feed_path: Path):
    """读上一次生成的 feed，返回 {guid: description}，用来避免重复抓取。"""
    import xml.etree.ElementTree as ET
    if not feed_path.exists():
        return {}
    try:
        root = ET.parse(feed_path).getroot()
    except ET.ParseError:
        return {}
    prev = {}
    for item in root.iter("item"):
        g, d = item.findtext("guid"), item.findtext("description")
        if g and d:
            prev[g.strip()] = d
    return prev


def parse_iso(s: str) -> datetime:
    s = s.strip().replace("Z", "+00:00")
    if len(s) == 10:
        return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
