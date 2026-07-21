# celestial-theme-forge

Reproducible tooling that expands the
[Celestial GTK theme](https://github.com/zquestz/celestial-gtk-theme) with the
**54-colour named Arc palette** from
[kiro-arc-themes](https://github.com/kirodubes/kiro-arc-themes) — turning the
stock 4 colours into **58 colours × 3 modes**, across every desktop surface
(GTK 2/3/4, GNOME Shell, Cinnamon, xfwm4, metacity, openbox, labwc, plank).

This folder is the **recipe**, not the output. It regenerates the per-colour
source files inside a celestial checkout; the theme itself is built and
installed from that checkout.

## How it works

Each new colour is generated as **"aliz with a different accent"**. Of the four
stock colours, `aliz` is the only one built on a neutral dark base (`#222222`),
so cloning it and swapping the accent yields a clean variant without dragging in
a tinted chrome (sea/azul use teal/blue-tinted darks).

The hard part is recolouring the baked image assets without touching colours
that must stay fixed (red close buttons, destructive/error reds, success green,
greys). The accent is isolated **empirically**: a hex is "accent" iff it appears
in an aliz asset but **not** in the matching `azul` asset (azul is the clean blue
sibling — its only reds are the universal semantic ones). This needs no
hand-maintained denylist and also **fixes an upstream aliz bug** where the
switch/toggle "on" slot was left green instead of the accent.

`src/colors.def` (written into the celestial checkout) is the single source of
truth — name → accent + dark chrome — and is sourced by celestial's
`install.sh`, `parse_sass.sh`, the three `render-assets.sh`, and the plank
renderer, all of which were made data-driven (no more hardcoded 4 names).

## Files

| File | Role |
|------|------|
| `generate-arc-colors.sh` | Main generator: writes `colors.def`, clones aliz's SCSS blocks, entry files, vector/text sources and assets, recolours each onto its accent. Idempotent. |
| `arc-colors-recolor.py` | Recolours one asset by isolating accent hexes via the aliz-minus-azul diff and reprojecting them onto the target hue. |
| `arc-colors-scss.py` | Clones the per-colour `@if $color == "aliz"` SCSS blocks. |
| `render-all.sh` | Renders all per-colour PNG assets in parallel across CPU cores (resumable). |
| `theme-forge-picker.py` | GTK4 app: pick a colour (screen eyedropper or swatch), look up real names online, then generate → build → install it into `~/.themes`. |
| `prepare-celestial.py` | Clones a celestial checkout if missing and patches it to be `colors.def`-driven. Idempotent. |
| `celestial-dir.sh` | Sourced helper: the single definition of how `CELESTIAL_DIR` is resolved. |
| `custom-colors.def` | Persistent `name hex` list of colours added via the picker / `--add` (created on first use). Merged into the generator's colour set so picks are reproducible. |

## Pick a colour interactively

```bash
python3 theme-forge-picker.py
```

**Pick from screen** uses the picker that matches the session — `xcolor` on X11,
`hyprpicker` on Wayland. X11 tools read the root window, which under Wayland
belongs to XWayland and holds no composited output, so `xcolor` there would
return black rather than fail. If the session's tool is missing the button is
disabled with a tooltip naming it.

Pick a colour from the screen (eyedropper) or a swatch, hit **Look up names
online** for real colour-name suggestions (from [color.pizza] and
[thecolorapi]), choose/edit the name, then **Create theme** — it runs the full
generate → compile → render → install pipeline and drops the theme in
`~/.themes`. The render step takes a few minutes (single colour, not the full
set). Picked colours are recorded in `custom-colors.def`, so they survive a
clean rebuild.

Headless equivalent (skips the GUI, adds + builds one colour):

```bash
./generate-arc-colors.sh --add <name> <hex>   # then steps 2-4 below
```

[color.pizza]: https://api.color.pizza
[thecolorapi]: https://www.thecolorapi.com

## Prerequisites

```bash
sudo pacman -S git sassc inkscape python imagemagick   # optipng optional (shrinks PNGs)
sudo pacman -S python-gobject gtk4                     # for theme-forge-picker.py
sudo pacman -S xcolor                                  # screen eyedropper on X11
sudo pacman -S hyprpicker                              # screen eyedropper on Wayland (wlroots)
```

## The theme checkout

The forge generates *into* a celestial-gtk-theme checkout. It finds one in this
order:

1. `$CELESTIAL_DIR`
2. this folder, if the theme source sits here too (`src/gtk` present)
3. `../celestial-gtk-theme` — a sibling of this folder
4. `/tmp/celestial-gtk-theme` — where a cloned checkout lands

Nothing there yet? Get one with:

```bash
./prepare-celestial.py                       # clones into /tmp/celestial-gtk-theme
./prepare-celestial.py --dir ~/celestial-gtk-theme
```

That clones upstream **and** patches it to be `colors.def`-driven, which the
generator requires (upstream hardcodes the four stock colour names in
`install.sh`, `parse_sass.sh`, the three `render-assets.sh` and
`render-plank-themes.sh`). It is idempotent — safe to re-run — and aborts loudly
rather than half-patching if upstream has moved. The picker exposes the same
thing as a **Get theme source** button, shown only when no checkout is found.

/tmp is the default because it is always writable and needs no assumptions about
your home layout; it is also wiped on reboot, so set `CELESTIAL_DIR` to keep a
checkout (a full render is ~630M).

## Rerun from scratch (e.g. after a celestial upgrade)

```bash
export CELESTIAL_DIR=/tmp/celestial-gtk-theme   # or wherever your checkout is

# 1. Generate every per-colour source file + colors.def (fast, ~30s)
./generate-arc-colors.sh
#    ...or a subset:  ./generate-arc-colors.sh crimson emerald

# 2. Compile SCSS -> CSS for every colour (~1-2 min)
"$CELESTIAL_DIR/parse_sass.sh"

# 3. Render all PNG assets in parallel (~1h on 16 cores; resumable)
./render-all.sh

# 4. Install into ~/.themes
"$CELESTIAL_DIR/install.sh"
```

To add or change a colour, edit the `COLORS` map at the top of
`generate-arc-colors.sh` (lowercase name → accent hex, hyphens kept) and re-run
the steps above. The generator strips and re-inserts its own SCSS blocks, so
re-running never duplicates.

## Starting from a pristine upstream clone

Nothing extra to do — `prepare-celestial.py` applies the data-driven edits to
`install.sh`, `parse_sass.sh`, `src/{gtk,gtk-2.0,xfwm4}/render-assets.sh` and
`src/plank/render-plank-themes.sh` for you. Run it against any checkout, fresh
or existing.
