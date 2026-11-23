"""Snapshot the six "Where is my money?" articles from the Wise help centre.

Wise renders each article from Contentful rich text embedded in the page.
We read that JSON instead of scraping HTML, so the output keeps the real
structure (headings, lists, links) and nothing else.

Usage: python scripts/fetch_faq.py [output_dir]   (default: data/faq)
Standard library only.
"""

import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

BASE = "https://wise.com/help/articles"
ARTICLES = [
    ("2452305", "how-do-i-check-my-transfers-status"),
    ("2941900", "when-will-my-money-arrive"),
    ("2977950", "why-does-it-say-my-transfers-complete-when-the-money-hasnt-arrived-yet"),
    ("2977951", "why-is-my-transfer-taking-longer-than-the-estimate"),
    ("2932689", "what-is-a-proof-of-payment"),
    ("2977938", "whats-a-banking-partner-reference-number"),
]
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept-Language": "en-GB,en"}


def fetch_article(url: str) -> dict:
    request = urllib.request.Request(url, headers=HEADERS)
    page = urllib.request.urlopen(request, timeout=30).read().decode("utf-8")
    next_data = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.DOTALL)
    queries = json.loads(next_data.group(1))["props"]["pageProps"]["_app"]["dehydratedState"]["queries"]
    article = next(q["state"]["data"] for q in queries if q["queryKey"][0] == "article")
    entry = json.loads(article["contentful"])["items"][0]
    return {
        "title": article["title"],
        "updated": entry["sys"]["updatedAt"][:10],
        "body": entry["fields"]["content"],
    }


def inline(node: dict) -> str:
    """Render text, bold and links inside a paragraph."""
    kind = node["nodeType"]
    if kind == "text":
        text = node["value"]
        if any(mark["type"] == "bold" for mark in node.get("marks", [])) and text.strip():
            lead = " " if text.startswith(" ") else ""
            trail = " " if text.endswith(" ") else ""
            return f"{lead}**{text.strip()}**{trail}"
        return text
    text = "".join(inline(child) for child in node.get("content", []))
    if kind == "hyperlink" and text.strip():
        uri = node["data"]["uri"]
        if uri.startswith("/"):
            uri = "https://wise.com" + uri
        return f"[{text.strip()}]({uri})" + (" " if text.endswith(" ") else "")
    return text  # entry-hyperlink and friends: keep the words, drop the internal id


def block(node: dict) -> list[str]:
    """Render a block node to markdown lines."""
    kind = node["nodeType"]
    children = node.get("content", [])
    if kind == "paragraph":
        text = re.sub(r"\s+", " ", "".join(inline(c) for c in children)).strip()
        return [text] if text else []
    if kind.startswith("heading-"):
        level = int(kind[-1])
        return ["#" * level + " " + "".join(inline(c) for c in children).strip()]
    if kind in ("unordered-list", "ordered-list"):
        lines = []
        for number, item in enumerate(children, 1):
            bullet = f"{number}. " if kind == "ordered-list" else "- "
            item_lines = [line for child in item["content"] for line in block(child)]
            lines.append(bullet + item_lines[0])
            lines.extend(" " * len(bullet) + line for line in item_lines[1:])
        return lines
    return [line for child in children for line in block(child)]


def to_markdown(article: dict, url: str) -> str:
    front = [
        "---",
        f'title: "{article["title"]}"',
        f"source: {url}",
        f"updated: {article['updated']}",
        f"fetched: {date.today().isoformat()}",
        "---",
        "",
        f"# {article['title']}",
        "",
    ]
    body: list[str] = []
    for node in article["body"]["content"]:
        lines = block(node)
        if lines:
            body.extend([*lines, ""])
    return "\n".join(front + body).rstrip() + "\n"


def main() -> None:
    default = Path(__file__).resolve().parents[1] / "data" / "faq"
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else default
    out_dir.mkdir(parents=True, exist_ok=True)
    for number, (article_id, slug) in enumerate(ARTICLES, 1):
        url = f"{BASE}/{article_id}/{slug}"
        article = fetch_article(url)
        path = out_dir / f"{number:02d}-{slug}.md"
        path.write_text(to_markdown(article, url), encoding="utf-8")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
