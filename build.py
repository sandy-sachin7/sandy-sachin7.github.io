#!/usr/bin/env python3
"""
Zero-dependency static site generator for sandy-sachin7.github.io.

Reads Markdown posts (personal essays, prose, general writing, and engineering notes)
from `content/posts/*.md` and builds `dist/` (HTML pages, Atom feed, sitemap,
robots.txt, and assets).

Usage:
    python3 build.py
"""
from __future__ import annotations

import html
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
POSTS_DIR = ROOT / "content" / "posts"
ASSETS_DIR = ROOT / "assets"
DIST_DIR = ROOT / "dist"
SITE_URL = "https://sandy-sachin7.github.io"
SITE_TITLE = "Santhosh Sachin"
SITE_DESC = (
    "Personal essays, prose, general writing, and software notes by Santhosh Sachin."
)

LITERARY_KINDS = {
    "personal",
    "prose",
    "essay",
    "essays",
    "fiction",
    "story",
    "poetry",
    "poem",
    "journal",
    "reflection",
    "reflections",
    "letters",
    "general",
    "culture",
    "books",
}

FONTS_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
    '  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
    '  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600'
    '&family=IBM+Plex+Sans:wght@400;500;600&family=Newsreader:ital,opsz,wght@0,6..72,400..600;'
    '1,6..72,400..500&display=swap" rel="stylesheet">'
)


@dataclass
class Post:
    title: str
    slug: str
    date: str
    kind: str
    style: str
    tags: list[str]
    summary: str
    read_time: str
    location: str
    epigraph: str
    excerpt: str
    metric: str
    metric_label: str
    metric_note: str
    repo_url: str
    featured: bool
    poster: str
    poster_alt: str
    body_md: str
    body_html: str

    @property
    def is_literary(self) -> bool:
        if self.style:
            return self.style.lower() in {"serif", "literary", "prose"}
        return self.kind.lower() in LITERARY_KINDS

    @property
    def filter_terms(self) -> list[str]:
        terms: list[str] = []
        seen: set[str] = set()
        for item in ([self.kind] if self.kind else []) + self.tags:
            key = item.strip().lower()
            if key and key not in seen:
                seen.add(key)
                terms.append(item.strip())
        return terms


def parse_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", raw, re.DOTALL)
    if not match:
        raise ValueError("Missing YAML frontmatter block")
    meta_block, body = match.group(1), match.group(2)
    meta: dict[str, str] = {}
    for line in meta_block.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        k, _, v = line.partition(":")
        meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, body


def estimate_read_time(md: str) -> str:
    plain = re.sub(r"```.*?```", " ", md, flags=re.DOTALL)
    plain = re.sub(r"<[^>]+>", " ", plain)
    words = len(re.findall(r"\b\w+\b", plain))
    mins = max(1, round(words / 220))
    return f"{mins} min"


def render_inline(text: str) -> str:
    # Protect inline code first
    code_tokens: list[str] = []

    def stash_code(m: re.Match[str]) -> str:
        code_tokens.append(f"<code>{html.escape(m.group(1))}</code>")
        return f"\x00CODE{len(code_tokens) - 1}\x00"

    text = re.sub(r"`([^`]+)`", stash_code, text)
    text = html.escape(text)
    # Links: [label](url)
    text = re.sub(
        r"\[([^\]]+)\]\((https?://[^\s)]+|/[^\s)]+)\)",
        r'<a href="\2">\1</a>',
        text,
    )
    # Strikethrough, bold, italic
    text = re.sub(r"~~([^~]+)~~", r"<del>\1</del>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)
    text = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"<em>\1</em>", text)

    for idx, token in enumerate(code_tokens):
        text = text.replace(f"\x00CODE{idx}\x00", token)
    return text


def render_verse_block(lines: list[str]) -> str:
    stanzas: list[list[str]] = []
    cur: list[str] = []
    for raw_line in lines:
        if not raw_line.strip():
            if cur:
                stanzas.append(cur)
                cur = []
        else:
            lead = len(raw_line) - len(raw_line.lstrip(" "))
            prefix = "&nbsp;" * lead
            cur.append(prefix + render_inline(raw_line.lstrip(" ")))
    if cur:
        stanzas.append(cur)
    stanza_html = "".join(f"<p>{'<br>'.join(stanza)}</p>" for stanza in stanzas)
    return f'<div class="verse">{stanza_html}</div>'


def render_markdown(md: str) -> str:
    lines = md.splitlines()
    out: list[str] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # Raw HTML block passthrough (for interactive widgets, embeds, and custom figures)
        if stripped.startswith(("<div ", "<section ", "<figure ")):
            html_lines = [line]
            depth = 1
            if stripped.startswith("<div "):
                tag = "div"
            elif stripped.startswith("<section "):
                tag = "section"
            else:
                tag = "figure"
            i += 1
            while i < n and depth > 0:
                cur = lines[i]
                depth += len(re.findall(rf"<{tag}\b", cur))
                depth -= len(re.findall(rf"</{tag}>", cur))
                html_lines.append(cur)
                i += 1
            out.append("\n".join(html_lines))
            continue

        # Scene break / thematic horizontal rule (---, ***, * * *)
        if re.match(r"^(?:-{3,}|\*{3,}|(?:\*\s+){2,}\*)$", stripped):
            out.append('<hr class="scene-break" aria-hidden="true">')
            i += 1
            continue

        # Fenced block (code or verse/poem)
        if stripped.startswith("```"):
            lang = stripped[3:].strip().lower()
            block_lines: list[str] = []
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                block_lines.append(lines[i])
                i += 1
            i += 1
            if lang in {"verse", "poem", "poetry"}:
                out.append(render_verse_block(block_lines))
            else:
                cls = f' class="language-{html.escape(lang)}"' if lang else ""
                code_escaped = html.escape("\n".join(block_lines))
                out.append(
                    '<div class="code-block">'
                    '<button type="button" class="copy-btn" aria-label="Copy code snippet">Copy</button>'
                    f"<pre><code{cls}>{code_escaped}</code></pre>"
                    "</div>"
                )
            continue

        # Headings
        if stripped.startswith("## "):
            title = stripped[3:].strip()
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
            out.append(f'<h2 id="{slug}">{render_inline(title)}</h2>')
            i += 1
            continue
        if stripped.startswith("### "):
            title = stripped[4:].strip()
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
            out.append(f'<h3 id="{slug}">{render_inline(title)}</h3>')
            i += 1
            continue

        # Blockquote (supports multiple paragraphs separated by bare `>`)
        if stripped.startswith(">"):
            q_paras: list[list[str]] = [[]]
            while i < n and lines[i].strip().startswith(">"):
                q_line = lines[i].strip()[1:].strip()
                if not q_line:
                    if q_paras[-1]:
                        q_paras.append([])
                else:
                    q_paras[-1].append(q_line)
                i += 1
            p_html = "".join(
                f"<p>{render_inline(' '.join(p))}</p>" for p in q_paras if p
            )
            out.append(f"<blockquote>{p_html}</blockquote>")
            continue

        # Markdown pipe table
        if stripped.startswith("|") and i + 1 < n and re.match(r"^\|[\s:\-|]+\|$", lines[i + 1].strip()):
            headers = [c.strip() for c in stripped.strip("|").split("|")]
            i += 2
            rows: list[list[str]] = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            ths = "".join(f"<th>{render_inline(h)}</th>" for h in headers)
            trs = []
            for r in rows:
                tds = "".join(f"<td>{render_inline(c)}</td>" for c in r)
                trs.append(f"<tr>{tds}</tr>")
            out.append(
                '<div class="table-scroll"><table>'
                f"<thead><tr>{ths}</tr></thead>"
                f"<tbody>{''.join(trs)}</tbody>"
                "</table></div>"
            )
            continue

        # Unordered list
        if stripped.startswith("- "):
            items: list[str] = []
            while i < n and lines[i].strip().startswith("- "):
                items.append(f"<li>{render_inline(lines[i].strip()[2:])}</li>")
                i += 1
            out.append(f"<ul>{''.join(items)}</ul>")
            continue

        # Ordered list
        if re.match(r"^\d+\.\s+", stripped):
            items = []
            while i < n and re.match(r"^\d+\.\s+", lines[i].strip()):
                item_txt = re.sub(r"^\d+\.\s+", "", lines[i].strip())
                items.append(f"<li>{render_inline(item_txt)}</li>")
                i += 1
            out.append(f"<ol>{''.join(items)}</ol>")
            continue

        # Standalone Markdown image: ![alt](src)
        img_match = re.match(r"^!\[([^\]]*)\]\((https?://[^\s)]+|/[^\s)]+)\)$", stripped)
        if img_match:
            alt_txt = html.escape(img_match.group(1))
            src_url = html.escape(img_match.group(2))
            caption = f"<figcaption>{alt_txt}</figcaption>" if alt_txt else ""
            out.append(
                f'<figure class="poster-figure">'
                f'<img src="{src_url}" alt="{alt_txt}" width="1600" height="900" loading="lazy">'
                f"{caption}</figure>"
            )
            i += 1
            continue

        # Paragraph
        p_lines = [stripped]
        i += 1
        while (
            i < n
            and lines[i].strip()
            and not lines[i].strip().startswith(("#", "```", ">", "- ", "|", "<div ", "<section ", "<figure ", "!["))
            and not re.match(r"^(?:-{3,}|\*{3,}|(?:\*\s+){2,}\*)$", lines[i].strip())
            and not re.match(r"^\d+\.\s+", lines[i].strip())
        ):
            p_lines.append(lines[i].strip())
            i += 1
        out.append(f"<p>{render_inline(' '.join(p_lines))}</p>")

    return "\n".join(out)


def load_posts() -> list[Post]:
    posts: list[Post] = []
    for path in sorted(POSTS_DIR.glob("*.md"), reverse=True):
        meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        tags = [t.strip() for t in meta.get("tags", "").split(",") if t.strip()]
        posts.append(
            Post(
                title=meta["title"],
                slug=meta["slug"],
                date=meta["date"],
                kind=meta.get("kind", ""),
                style=meta.get("style", ""),
                tags=tags,
                summary=meta["summary"],
                read_time=meta.get("read_time") or estimate_read_time(body),
                location=meta.get("location", ""),
                epigraph=meta.get("epigraph", ""),
                excerpt=meta.get("excerpt", ""),
                metric=meta.get("metric", ""),
                metric_label=meta.get("metric_label", ""),
                metric_note=meta.get("metric_note", ""),
                repo_url=meta.get("repo_url", ""),
                featured=meta.get("featured", "false").lower() == "true",
                poster=meta.get("poster", ""),
                poster_alt=meta.get("poster_alt", ""),
                body_md=body,
                body_html=render_markdown(body),
            )
        )
    posts.sort(key=lambda p: p.date, reverse=True)
    return posts


def render_shell(
    *,
    title: str,
    description: str,
    canonical: str,
    og_type: str,
    og_image: str,
    og_image_alt: str,
    json_ld: dict,
    body_html: str,
    is_home: bool = False,
    show_progress: bool = False,
) -> str:
    progress = '<div id="reading-progress" class="progress-bar" aria-hidden="true"></div>' if show_progress else ""
    writing_href = "#writing" if is_home else "/#writing"
    tools_href = "#tools" if is_home else "/#tools"
    ld_json = json.dumps(json_ld, ensure_ascii=False)
    full_og_image = og_image if og_image.startswith("http") else f"{SITE_URL}{og_image}"
    return f"""<!doctype html>
<html lang="en" data-theme="light">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <meta name="description" content="{html.escape(description)}">
  <link rel="canonical" href="{html.escape(canonical)}">
  <link rel="alternate" type="application/atom+xml" title="{html.escape(SITE_TITLE)} Atom Feed" href="{SITE_URL}/feed.xml">
  <meta property="og:title" content="{html.escape(title)}">
  <meta property="og:description" content="{html.escape(description)}">
  <meta property="og:type" content="{og_type}">
  <meta property="og:url" content="{html.escape(canonical)}">
  <meta property="og:image" content="{html.escape(full_og_image)}">
  <meta property="og:image:width" content="1600">
  <meta property="og:image:height" content="900">
  <meta property="og:image:alt" content="{html.escape(og_image_alt)}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:image" content="{html.escape(full_og_image)}">
  {FONTS_LINK}
  <link rel="stylesheet" href="/assets/style.css">
  <script type="application/ld+json">{ld_json}</script>
  <script>
    (function(){{try{{var t=localStorage.getItem("sachin-theme");if(t==="dark"||t==="light"){{document.documentElement.setAttribute("data-theme",t);}}else if(window.matchMedia&&window.matchMedia("(prefers-color-scheme: dark)").matches){{document.documentElement.setAttribute("data-theme","dark");}}}}catch(e){{}}}})();
  </script>
</head>
<body>
  <a class="skip-link" href="#main-content">Skip to content</a>
  {progress}
  <header class="masthead">
    <div class="wrap">
      <div class="masthead-inner">
        <a class="brand" href="/">{html.escape(SITE_TITLE)}</a>
        <nav class="nav" aria-label="Primary">
          <a href="{writing_href}"{' aria-current="page"' if is_home else ''}>Writing</a>
          <a href="{tools_href}">Software</a>
          <a href="/feed.xml">RSS</a>
          <button type="button" id="theme-toggle" class="theme-toggle" aria-pressed="false" aria-label="Switch to Ink dark theme">Ink</button>
        </nav>
      </div>
    </div>
  </header>
  <main id="main-content">
    {body_html}
  </main>
  <footer class="site-footer">
    <div class="wrap footer-inner">
      <span>Santhosh Sachin, Coimbatore.</span>
      <div class="footer-links">
        <a href="https://github.com/sandy-sachin7">GitHub</a>
        <a href="https://x.com/santhoshssachin">X</a>
        <a href="/feed.xml">Atom Feed</a>
      </div>
    </div>
  </footer>
  <script src="/assets/site.js" defer></script>
</body>
</html>
"""


def build_featured_section(featured: Post) -> str:
    label_parts = [featured.kind or "Featured", featured.date]
    label = " / ".join(label_parts)
    cta_label = "Read the piece" if featured.is_literary else "Read the essay"

    aside_html = ""
    section_cls = "featured"
    if featured.metric:
        metric_label = featured.metric_label or "Highlight"
        aside_html = f"""
        <div class="featured-proof">
          <p class="section-label">{html.escape(metric_label)}</p>
          <p class="proof-stat">{html.escape(featured.metric)}</p>
          <p class="proof-note">{html.escape(featured.metric_note)}</p>
        </div>"""
    elif featured.excerpt:
        aside_html = f"""
        <blockquote class="featured-excerpt">
          <p>{render_inline(featured.excerpt)}</p>
        </blockquote>"""
    else:
        section_cls = "featured featured--single"

    return f"""
      <section class="{section_cls}" aria-label="Featured writing">
        <div>
          <p class="section-label">{html.escape(label)}</p>
          <h2><a href="/posts/{featured.slug}/">{html.escape(featured.title)}</a></h2>
          <p>{html.escape(featured.summary)}</p>
          <a class="cta-link" href="/posts/{featured.slug}/">{cta_label}</a>
        </div>{aside_html}
      </section>"""


def build_home(posts: list[Post]) -> str:
    featured = next((p for p in posts if p.featured), posts[0])

    # Filter by top-level post kind so the bar stays compact as tags grow
    filter_labels: list[str] = []
    seen_filters: set[str] = set()
    for p in posts:
        if p.kind and p.kind.lower() not in seen_filters:
            seen_filters.add(p.kind.lower())
            filter_labels.append(p.kind)

    filter_btns = ['<button type="button" class="filter-btn" data-filter="all" aria-pressed="true">All</button>']
    for label in filter_labels:
        slug = label.lower()
        filter_btns.append(
            f'<button type="button" class="filter-btn" data-filter="{html.escape(slug)}" aria-pressed="false">{html.escape(label)}</button>'
        )

    rows_html: list[str] = []
    for idx, p in enumerate(posts, start=1):
        num = f"{idx:02d}"
        filter_csv = ",".join(t.lower() for t in p.filter_terms)
        kind_span = f'<span class="essay-kind">{html.escape(p.kind)}</span>' if p.kind else ""
        display_tags = [t for t in p.tags if t.lower() != p.kind.lower()]
        tags_spans = "".join(f"<span>#{html.escape(t)}</span>" for t in display_tags)
        meta_line = f"{html.escape(p.date)}<br>{html.escape(p.read_time)}"
        rows_html.append(
            f'<li class="essay-row" data-tags="{html.escape(filter_csv)}">'
            f'  <span class="essay-num">{num}</span>'
            f'  <div>'
            f'    <h3 class="essay-title"><a href="/posts/{p.slug}/">{html.escape(p.title)}</a></h3>'
            f'    <p class="essay-summary">{html.escape(p.summary)}</p>'
            f'    <div class="essay-tags">{kind_span}{tags_spans}</div>'
            f'  </div>'
            f'  <div class="essay-meta">{meta_line}</div>'
            f'</li>'
        )

    featured_html = build_featured_section(featured)

    body = f"""
    <div class="wrap">
      <section class="opener" aria-label="Introduction">
        <div>
          <h1>Essays, prose, and software.</h1>
          <p class="opener-lead">
            A personal notebook for essays, short prose, general thoughts, and technical field notes. Some posts carry Rust code and benchmarks; others are just things worth thinking through in public.
          </p>
        </div>
        <aside class="colophon" aria-label="Author details">
          <dl>
            <dt>Based</dt>
            <dd>Coimbatore, India</dd>
            <dt>Writing</dt>
            <dd>Personal essays, prose, general notes, and engineering</dd>
            <dt>Elsewhere</dt>
            <dd class="colophon-links">
              <a href="https://github.com/sandy-sachin7">GitHub</a>
              <a href="https://x.com/santhoshssachin">X</a>
              <a href="/feed.xml">RSS</a>
            </dd>
          </dl>
        </aside>
      </section>
      {featured_html}

      <section class="section-block" id="writing" aria-labelledby="writing-heading">
        <div class="section-head">
          <h2 id="writing-heading">Writing</h2>
          <div class="filter-bar" role="group" aria-label="Filter writing by topic">
            {''.join(filter_btns)}
          </div>
        </div>
        <ol class="essay-list">
          {''.join(rows_html)}
        </ol>
        <div id="filter-empty" class="empty-state hidden" role="status">
          <p>No published pieces match that topic yet.</p>
          <button type="button" id="filter-reset">Show all writing</button>
        </div>
      </section>

      <section class="section-block" id="tools" aria-labelledby="tools-heading">
        <div class="section-head">
          <h2 id="tools-heading">Software &amp; open source</h2>
        </div>
        <div class="tools-ledger">
          <div class="tool-row">
            <div>
              <h3 class="tool-name"><a href="https://github.com/sandy-sachin7/deltalens">deltalens</a></h3>
              <div class="tool-ver">Rust / v2.1.0 / MIT</div>
            </div>
            <div>
              <p class="tool-desc">Read-only CLI and library to inspect, diff, trace, and CI-gate Delta Lake tables directly from _delta_log/ across local disk, S3, GCS, and Azure ADLS, with delta-rs differential conformance tests and strict reader feature checks.</p>
              <div class="tool-links">
                <a href="https://github.com/sandy-sachin7/deltalens">Source</a>
                <a href="https://sandy-sachin7.github.io/deltalens/">Benchmarks</a>
                <a href="https://crates.io/crates/deltalens">Crates.io</a>
              </div>
            </div>
            <div class="tool-metric">2.91 ms cold CLI / 12.5 MB RSS<br>111 ms / 89 MB on 50k files</div>
          </div>

          <div class="tool-row">
            <div>
              <h3 class="tool-name"><a href="https://github.com/sandy-sachin7/contextd">contextd</a></h3>
              <div class="tool-ver">Rust / v4.1.0 / MIT</div>
            </div>
            <div>
              <p class="tool-desc">Local-first semantic search and MCP daemon using Tree-sitter AST chunking, int8 or FP32 ONNX Runtime embeddings, and SQLite WAL (sqlite-vec plus FTS5) with loopback hardening and atomic index rollback.</p>
              <div class="tool-links">
                <a href="https://github.com/sandy-sachin7/contextd">Source</a>
                <a href="https://sandy-sachin7.github.io/contextd/">Docs</a>
                <a href="https://crates.io/crates/contextd">Crates.io</a>
              </div>
            </div>
            <div class="tool-metric">4.84 ms p50 hybrid query (int8)<br>33.99 s repo index / 1.000 R@10</div>
          </div>

          <div class="tool-row">
            <div>
              <h3 class="tool-name"><a href="https://github.com/sandy-sachin7/shard">shard</a></h3>
              <div class="tool-ver">Rust + PyO3 / v2.5.0 / MIT</div>
            </div>
            <div>
              <p class="tool-desc">Content-addressed, Ed25519-signed version control and libp2p sync for ML artifacts using FastCDC content-defined chunking, Blake3, AES-256-GCM envelopes, and transactional staged checkout.</p>
              <div class="tool-links">
                <a href="https://github.com/sandy-sachin7/shard">Source</a>
                <a href="https://sandy-sachin7.github.io/shard/">Docs</a>
                <a href="https://pypi.org/project/shard-py/">PyPI</a>
              </div>
            </div>
            <div class="tool-metric">98.5% FastCDC dedup on shifts<br>89.0% on frozen 90% checkpoints</div>
          </div>
        </div>
      </section>
    </div>
    """

    json_ld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Person",
                "name": "Santhosh Sachin",
                "url": f"{SITE_URL}/",
                "sameAs": [
                    "https://github.com/sandy-sachin7",
                    "https://x.com/santhoshssachin",
                ],
                "homeLocation": {"@type": "Place", "name": "Coimbatore, India"},
            },
            {
                "@type": "WebSite",
                "name": SITE_TITLE,
                "url": f"{SITE_URL}/",
                "description": SITE_DESC,
            },
        ],
    }

    return render_shell(
        title=f"{SITE_TITLE} | Essays, Prose, and Software",
        description=SITE_DESC,
        canonical=f"{SITE_URL}/",
        og_type="website",
        og_image="/assets/blog-og.png",
        og_image_alt="Santhosh Sachin: Essays, prose, and software. Personal writing, general notes, and open-source tools.",
        json_ld=json_ld,
        body_html=body,
        is_home=True,
        show_progress=False,
    )


def build_post_page(post: Post, prev_post: Post | None, next_post: Post | None) -> str:
    canonical = f"{SITE_URL}/posts/{post.slug}/"

    meta_items: list[str] = [f'<time datetime="{html.escape(post.date)}">{html.escape(post.date)}</time>']
    if post.location:
        meta_items.append(f"<span>{html.escape(post.location)}</span>")
    meta_items.append(f"<span>{html.escape(post.read_time)} read</span>")
    if post.kind:
        meta_items.append(f'<span class="meta-kind">{html.escape(post.kind)}</span>')
    if post.tags:
        display_tags = [t for t in post.tags if t.lower() != post.kind.lower()]
        if display_tags:
            tags_html = " ".join(f"<span>#{html.escape(t)}</span>" for t in display_tags)
            meta_items.append(f"<span>{tags_html}</span>")
    if post.repo_url:
        meta_items.append(f'<a href="{html.escape(post.repo_url)}">Repository</a>')

    nav_left = (
        f'<a href="/posts/{prev_post.slug}/">Previous: {html.escape(prev_post.title)}</a>'
        if prev_post
        else '<a href="/">Back to all writing</a>'
    )
    if next_post:
        nav_right = f'<a href="/posts/{next_post.slug}/">Next: {html.escape(next_post.title)}</a>'
    elif post.repo_url:
        nav_right = f'<a href="{html.escape(post.repo_url)}">View source on GitHub</a>'
    else:
        nav_right = '<a href="/#writing">All writing</a>'

    poster_html = ""
    if post.poster:
        alt_text = post.poster_alt or post.title
        poster_html = (
            f'<figure class="poster-figure">'
            f'<img src="{html.escape(post.poster)}" alt="{html.escape(alt_text)}" width="1600" height="900" loading="eager" fetchpriority="high">'
            f'<figcaption>{html.escape(alt_text)}</figcaption>'
            f"</figure>"
        )

    epigraph_html = ""
    if post.epigraph:
        epigraph_html = f'<blockquote class="epigraph"><p>{render_inline(post.epigraph)}</p></blockquote>'

    crumb_tail = html.escape(post.kind or post.slug)
    prose_cls = "prose prose--literary" if post.is_literary else "prose"

    body = f"""
    <article class="article-wrap">
      <div class="breadcrumb"><a href="/">Home</a> / <a href="/#writing">Writing</a> / {crumb_tail}</div>
      <header class="article-header">
        <h1>{html.escape(post.title)}</h1>
        <p class="article-dek">{html.escape(post.summary)}</p>
        <div class="article-meta">
          {''.join(meta_items)}
        </div>
      </header>
      {poster_html}
      {epigraph_html}
      <div class="{prose_cls}">
        {post.body_html}
      </div>
      <footer class="article-footer" aria-label="Post navigation">
        <div>{nav_left}</div>
        <div>{nav_right}</div>
      </footer>
    </article>
    """

    post_og_image = post.poster or "/assets/blog-og.png"
    post_og_alt = post.poster_alt or post.title
    full_post_image = post_og_image if post_og_image.startswith("http") else f"{SITE_URL}{post_og_image}"

    json_ld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "BlogPosting",
                "headline": post.title,
                "description": post.summary,
                "image": full_post_image,
                "datePublished": post.date,
                "dateModified": post.date,
                "mainEntityOfPage": canonical,
                "author": {
                    "@type": "Person",
                    "name": "Santhosh Sachin",
                    "url": f"{SITE_URL}/",
                },
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{SITE_URL}/"},
                    {"@type": "ListItem", "position": 2, "name": post.title, "item": canonical},
                ],
            },
        ],
    }

    return render_shell(
        title=f"{post.title} | {SITE_TITLE}",
        description=post.summary,
        canonical=canonical,
        og_type="article",
        og_image=post_og_image,
        og_image_alt=post_og_alt,
        json_ld=json_ld,
        body_html=body,
        is_home=False,
        show_progress=True,
    )


def build_atom_feed(posts: list[Post]) -> str:
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entries = []
    for p in posts:
        url = f"{SITE_URL}/posts/{p.slug}/"
        entries.append(
            f"""  <entry>
    <title>{html.escape(p.title)}</title>
    <link href="{url}"/>
    <id>{url}</id>
    <updated>{p.date}T00:00:00Z</updated>
    <summary>{html.escape(p.summary)}</summary>
  </entry>"""
        )
    return f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>{html.escape(SITE_TITLE)}</title>
  <subtitle>{html.escape(SITE_DESC)}</subtitle>
  <link href="{SITE_URL}/feed.xml" rel="self"/>
  <link href="{SITE_URL}/"/>
  <updated>{updated}</updated>
  <id>{SITE_URL}/</id>
  <author><name>{html.escape(SITE_TITLE)}</name></author>
{chr(10).join(entries)}
</feed>
"""


def build_sitemap(posts: list[Post]) -> str:
    urls = [f"  <url><loc>{SITE_URL}/</loc></url>"]
    for p in posts:
        urls.append(f"  <url><loc>{SITE_URL}/posts/{p.slug}/</loc><lastmod>{p.date}</lastmod></url>")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>\n"
    )


def main() -> None:
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True)
    shutil.copytree(ASSETS_DIR, DIST_DIR / "assets", ignore=shutil.ignore_patterns("*.hype.md"))

    posts = load_posts()
    (DIST_DIR / "index.html").write_text(build_home(posts), encoding="utf-8")

    for i, post in enumerate(posts):
        post_dir = DIST_DIR / "posts" / post.slug
        post_dir.mkdir(parents=True, exist_ok=True)
        prev_p = posts[i + 1] if i + 1 < len(posts) else None
        next_p = posts[i - 1] if i > 0 else None
        (post_dir / "index.html").write_text(build_post_page(post, prev_p, next_p), encoding="utf-8")

    (DIST_DIR / "feed.xml").write_text(build_atom_feed(posts), encoding="utf-8")
    (DIST_DIR / "sitemap.xml").write_text(build_sitemap(posts), encoding="utf-8")
    (DIST_DIR / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n",
        encoding="utf-8",
    )
    print(f"Built {len(posts)} posts into {DIST_DIR}")


if __name__ == "__main__":
    main()
