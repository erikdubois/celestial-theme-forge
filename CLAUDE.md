# CLAUDE.md — celestial-theme-forge

## What this is

The reproducible generator that adds the 54-colour Arc palette to the Celestial
GTK theme. This folder is **tooling only** — the theme source and built output
live in the celestial checkout. That checkout is resolved by
[celestial-dir.sh](./celestial-dir.sh) / `resolve_celestial_dir()`:
`$CELESTIAL_DIR` → this folder → sibling `../celestial-gtk-theme` →
`/tmp/celestial-gtk-theme`. No path is tied to a username. See
[README.md](./README.md) for the full workflow.

## Key decisions (don't relearn these)

- **Template = `aliz`**, sibling = `azul`. New colour = "aliz with a different
  accent" because aliz is the only stock colour on a neutral `#222222` base.
- **Accent isolation is empirical**: accent hexes = those in an aliz asset but
  NOT in the matching azul asset. This protects semantic reds (close /
  destructive / error), success-green, structural greys, and a stray upstream
  Arc-blue — no hand-maintained denylist. Implemented in `arc-colors-recolor.py`
  (`accent_hexes()` does the per-file set difference; shades reproject onto the
  target hue preserving each shade's HSL offset from the red base `#f0544c` or
  green switch-slot base `#2eb398`).
- **Validate on a contrasting hue (purpley/emerald), never crimson** — crimson
  is red like aliz and hides both a bad semantic-red shift and the green-switch
  bug.
- **PNG-only assets** (thumbnails, labwc buttons) have no vector source, so they
  are hue-rotated with ImageMagick `-modulate` instead of the precise recolour.
- `colors.def` is the single source of truth; celestial's `install.sh`,
  `parse_sass.sh`, `render-assets.sh` (×3) and plank renderer source it.
- **Upstream does not ship those data-driven edits** — `prepare-celestial.py`
  applies them to any checkout via exact-string anchors, idempotently, and
  `sys.exit`s if an anchor is gone (upstream moved) rather than half-patching.
  Its output was verified byte-identical to the hand-patched working checkout.

## Gotchas

- The generator edits celestial's 4 `_colors.scss` files in place (idempotent
  strip + re-insert via sentinel comments). Re-running is safe.
- `render-all.sh` is resumable (skips existing PNGs). The full render is ~50k
  Inkscape calls — parallelised across cores.
- `optipng` is optional; render scripts skip it if absent.
