#!/usr/bin/env python3
"""
Sync SidelineSwap's Zendesk Help Center into this repo as Markdown.

Pulls every published article from the public Zendesk Guide API and writes:
  - articles/<id>-<slug>.md   one file per article (YAML frontmatter + body)
  - index.md                  human-readable table of contents, grouped by category/section
  - index.json                machine-readable index for Claude skills to consume

This is a READ-ONLY mirror. It never writes back to Zendesk.
Zendesk (help.sidelineswap.com) stays the source of truth; this repo is the copy.
"""

import os
import re
import json
import shutil
from collections import defaultdict
from datetime import datetime, timezone

import requests
from markdownify import markdownify as md, ATX

SUBDOMAIN = os.environ.get("ZENDESK_SUBDOMAIN", "sidelineswap")
LOCALE = os.environ.get("HELP_CENTER_LOCALE", "en-us")
BASE = f"https://{SUBDOMAIN}.zendesk.com/api/v2/help_center/{LOCALE}"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARTICLES_DIR = os.path.join(ROOT, "articles")


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def get_paginated(url, key):
    """Follow Zendesk's next_page links, collecting every item under `key`."""
    items = []
    params = {"per_page": 100}
    while url:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        items.extend(data.get(key, []))
        url = data.get("next_page")   # full URL, already carries pagination state
        params = {}
    return items


def fetch_all():
    articles = get_paginated(f"{BASE}/articles.json", "articles")
    sections = get_paginated(f"{BASE}/sections.json", "sections")
    categories = get_paginated(f"{BASE}/categories.json", "categories")
    return articles, sections, categories


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def slugify(title):
    slug = re.sub(r"[^\w\s-]", "", (title or "").lower()).strip()
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug[:60] or "untitled"


def yaml_escape(value):
    """Quote a scalar so it survives a YAML frontmatter parser."""
    if value is None:
        return '""'
    s = str(value)
    needs_quote = (
        s == ""
        or re.search(r'[:#\[\]{}",|?\n]', s)
        or s[0] in "!&*?|>%@`'\"-# "
        or s[-1] == " "
    )
    if needs_quote:
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


def render_article(article, section_name, category_name):
    labels = article.get("label_names") or []
    body_md = md(article.get("body") or "", heading_style=ATX).strip()
    updated = article.get("edited_at") or article.get("updated_at", "")

    lines = ["---",
             f"id: {article['id']}",
             f"title: {yaml_escape(article.get('title', ''))}",
             f"section: {yaml_escape(section_name)}",
             f"section_id: {article.get('section_id', '')}",
             f"category: {yaml_escape(category_name)}"]
    if labels:
        lines.append("labels: [" + ", ".join(yaml_escape(l) for l in labels) + "]")
    else:
        lines.append("labels: []")
    lines += [f"updated_at: {yaml_escape(updated)}",
              f"url: {yaml_escape(article.get('html_url', ''))}",
              "---",
              "",
              f"# {article.get('title', '')}",
              "",
              body_md,
              ""]
    return "\n".join(lines)


def _cell(text):
    """Escape a value for a markdown table cell."""
    return str(text or "").replace("|", "\\|").replace("\n", " ")


def write_index_md(entries):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = ["# SidelineSwap Help Center — Mirror Index",
             "",
             f"_Auto-generated. {len(entries)} published articles. Last synced {now}._",
             "",
             "Read-only mirror of help.sidelineswap.com. Zendesk is the source of truth — "
             "edit articles there, never here.",
             ""]

    grouped = defaultdict(lambda: defaultdict(list))
    for e in entries:
        grouped[e["category"] or "Uncategorized"][e["section"] or "General"].append(e)

    for category in sorted(grouped):
        lines += [f"## {category}", ""]
        for section in sorted(grouped[category]):
            lines += [f"### {section}", "",
                      "| Article | Labels | Updated | File |",
                      "| --- | --- | --- | --- |"]
            for e in sorted(grouped[category][section], key=lambda x: x["title"].lower()):
                lines.append(
                    f"| [{_cell(e['title'])}]({e['url']}) "
                    f"| {_cell(', '.join(e['labels']))} "
                    f"| {(e['updated_at'] or '')[:10]} "
                    f"| `{e['file']}` |"
                )
            lines.append("")
    with open(os.path.join(ROOT, "index.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def write_index_json(entries):
    payload = {
        "source": "help.sidelineswap.com",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "article_count": len(entries),
        "articles": entries,
    }
    with open(os.path.join(ROOT, "index.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def write_outputs(articles, sections, categories):
    section_by_id = {s["id"]: s for s in sections}
    category_by_id = {c["id"]: c for c in categories}

    # Rebuild the articles dir from scratch so deleted/unpublished articles
    # drop out of the mirror instead of lingering.
    if os.path.exists(ARTICLES_DIR):
        shutil.rmtree(ARTICLES_DIR)
    os.makedirs(ARTICLES_DIR, exist_ok=True)

    entries = []
    for a in articles:
        if a.get("draft"):
            continue
        section = section_by_id.get(a.get("section_id"), {})
        section_name = section.get("name", "")
        category = category_by_id.get(section.get("category_id"), {})
        category_name = category.get("name", "")

        filename = f"{a['id']}-{slugify(a.get('title', ''))}.md"
        with open(os.path.join(ARTICLES_DIR, filename), "w", encoding="utf-8") as f:
            f.write(render_article(a, section_name, category_name))

        entries.append({
            "id": a["id"],
            "title": a.get("title", ""),
            "section": section_name,
            "category": category_name,
            "labels": a.get("label_names") or [],
            "updated_at": a.get("edited_at") or a.get("updated_at", ""),
            "url": a.get("html_url", ""),
            "file": f"articles/{filename}",
        })

    entries.sort(key=lambda x: x["title"].lower())
    write_index_md(entries)
    write_index_json(entries)
    return entries


def main():
    print(f"Fetching from {BASE} ...")
    articles, sections, categories = fetch_all()
    print(f"Fetched {len(articles)} articles, {len(sections)} sections, "
          f"{len(categories)} categories.")
    entries = write_outputs(articles, sections, categories)
    print(f"Wrote {len(entries)} article files + index.md + index.json.")


if __name__ == "__main__":
    main()
