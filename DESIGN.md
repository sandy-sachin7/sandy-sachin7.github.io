# Design Direction: sandy-sachin7.github.io

## Identity
- Author: Santhosh Sachin (`sandy-sachin7`), systems engineer in Coimbatore, India.
- Voice: direct, measured, first-person engineering notes backed by reproducible scripts. No hype, no em dashes, no unverified numbers.
- Aesthetic: editorial print journal meets systems lab notebook.

## Palette (WCAG AA verified with contrast-check.py)
Two core neutrals plus one editorial accent per mode.

### Light mode (default, Archival Paper)
- Canvas (`--bg`): `#F6F3EC`
- Surface (`--surface`): `#EAE4D6`
- Primary ink (`--ink`): `#171614` (16.32:1 on canvas, 14.27:1 on surface)
- Secondary ink (`--muted`): `#4E4A42` (7.96:1 on canvas, 6.95:1 on surface)
- Accent (`--accent`): `#A83316` (6.02:1 on canvas, 5.26:1 on surface)
- Control border (`--border-strong`): `#736C60` (4.69:1 on canvas)
- Subtle hairline (`--rule`): `#D3CBB9`
- Positive metric highlight (`--good`): `#1B6B46` (5.85:1 on canvas)

### Dark mode (Lab Bench Ink)
- Canvas (`--bg`): `#141311`
- Surface (`--surface`): `#1E1C19`
- Primary ink (`--ink`): `#F0ECE2` (15.74:1 on canvas, 14.41:1 on surface)
- Secondary ink (`--muted`): `#B5AEA0` (8.42:1 on canvas, 7.71:1 on surface)
- Accent (`--accent`): `#F0714B` (6.34:1 on canvas, 5.80:1 on surface)
- Control border (`--border-strong`): `#7E776B` (4.19:1 on canvas)
- Subtle hairline (`--rule`): `#2F2C27`
- Positive metric highlight (`--good`): `#58C78B` (8.80:1 on canvas)

## Typography
- Display and article titles: `Newsreader` (optical serif, Georgia fallback) for editorial print authority.
- Body and UI controls: `IBM Plex Sans` (system sans fallback) for legible technical prose.
- Benchmarks, CLI output, and dates: `IBM Plex Mono` (`font-variant-numeric: tabular-nums`) so numbers align cleanly across tables.
- Fluid scale via `clamp()` across all viewports.

## Layout and Motif
- Motif: double-rule masthead (`2px` primary ink over `1px` hairline), folio index numbers (`01`, `02`, `03`), and structured tabular ledgers instead of identical card grids.
- Breakpoints (3 states): narrow (<640px, single-column compact register), medium (640px to 960px, reflowed ledger and two-column intro), wide (>960px, full editorial measure with marginalia).
- Touch and keyboard: minimum 44x44px tap targets on interactive controls, `cursor: pointer` on enabled buttons, visible 2px `:focus-visible` outlines in `--accent`.
