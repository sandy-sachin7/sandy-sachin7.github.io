# sandy-sachin7.github.io

Personal engineering journal and benchmark notes for Santhosh Sachin, built with a zero-dependency Python static site generator and deployed to GitHub Pages.

## Add a new post

1. Create a Markdown file in `content/posts/YYYY-MM-DD-your-slug.md` with frontmatter:

```markdown
---
title: "Post title"
slug: "your-slug"
date: "2026-11-26"
tags: "Rust, Storage"
summary: "One or two concrete sentences."
read_time: "5 min"
metric: "Optional headline metric"
metric_note: "Optional context"
repo_url: "https://github.com/sandy-sachin7/deltalens"
featured: "false"
---
```

2. Build and preview locally:

```bash
python3 build.py
python3 -m http.server 8000 --directory dist
```

3. Push to `main`. GitHub Actions builds `dist/` and deploys to `https://sandy-sachin7.github.io/` automatically.
