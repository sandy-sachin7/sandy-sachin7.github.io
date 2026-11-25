# sandy-sachin7.github.io

Personal blog and notebook for Santhosh Sachin: essays, prose, general writing, and engineering notes. Built with a zero-dependency Python static site generator and deployed to GitHub Pages.

## Add a new post

Create a Markdown file in `content/posts/YYYY-MM-DD-your-slug.md`.

### Personal essay, prose, or general post

Only `title`, `slug`, `date`, and `summary` are required. `read_time` is calculated automatically from word count if omitted. Posts with `kind` set to `Personal`, `Prose`, `Essay`, `Fiction`, `Poetry`, `Journal`, or `Reflection` automatically render in `Newsreader` serif with literary spacing and scene breaks.

```markdown
---
title: "Late evening rain in Coimbatore"
slug: "late-evening-rain-in-coimbatore"
date: "2026-11-26"
kind: "Prose"
tags: "Personal, Place"
location: "Coimbatore"
summary: "A short piece on monsoon evenings and empty streets."
epigraph: "Optional opening quote or line."
excerpt: "Optional pull-quote shown when featured on the homepage."
featured: "false"
---

Opening paragraph here.

* * *

Use `---` or `* * *` for a centered scene break.

```verse
Use a fenced verse block
for poetry or lines
where every break matters.
```
```

### Technical or benchmark post

Technical posts use `IBM Plex Sans` for body text and support optional `repo_url`, `poster`, `metric`, `metric_label`, and `metric_note` fields:

```markdown
---
title: "Post title"
slug: "your-slug"
date: "2026-11-26"
kind: "Engineering"
tags: "Rust, Storage"
summary: "One or two concrete sentences."
repo_url: "https://github.com/sandy-sachin7/deltalens"
metric: "Optional headline metric"
metric_label: "Optional benchmark context"
metric_note: "Optional explanation"
featured: "false"
---
```

## Build and preview locally

```bash
python3 build.py
python3 -m http.server 8000 --directory dist
```

Push to `main`. GitHub Actions builds `dist/` and deploys to `https://sandy-sachin7.github.io/`.
