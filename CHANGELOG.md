# Changelog

## 2026.06.27

### What Changed

- Initial extraction of the celestial colour generator into its own reproducible
  forge, so the 54-colour Arc expansion can be re-run against a future celestial
  release. Holds `generate-arc-colors.sh`, `arc-colors-recolor.py`,
  `arc-colors-scss.py` and `render-all.sh` plus docs.

### Technical Details

- Scripts auto-detect the target celestial checkout: `$CELESTIAL_DIR` if set,
  else the script's own dir when it contains `src/gtk`, else the default
  `/home/erik/DATA/celestial-gtk-theme`. Python helpers are path-agnostic
  (operate on paths passed as args).
- Accent isolation uses an aliz-minus-azul per-file hex diff (see CLAUDE.md);
  this both avoids touching semantic colours and fixes the upstream aliz
  green-switch bug.
- Added `theme-forge-picker.py`, a GTK4 app to pick a colour, research its name
  online and build+install a theme without hand-editing the generator. Backed by
  a new `--add NAME HEX` generator flag and a persistent `custom-colors.def`.
- Added a `PKGBUILD` (`celestial-theme-forge`, CalVer `26.06`) packaging the
  tooling into `/usr/share/celestial-theme-forge/` with `celestial-theme-forge`
  and `theme-forge-picker` exec wrappers on PATH. Wrappers `exec` the real
  scripts (not symlinks) so `BASH_SOURCE`/`__file__` resolve to the share dir and
  sibling scripts are found.
- Made `custom-colors.def` location writable-aware: in-tree for a writable dev
  checkout, else `$XDG_CONFIG_HOME/celestial-theme-forge/custom-colors.def`. This
  lets `--add` and the GUI's Create button work from the read-only installed copy.
- Added `theme-forge-picker.desktop` (installed to `/usr/share/applications/`) so
  the GUI appears in the application menu under Settings. Uses the stock
  `preferences-desktop-theme` icon.
- Picker "Choose…" now opens the colour editor pre-set to the current colour.
  `Gtk.ColorDialog` only selected it in the palette grid (leaving the editor on
  its default red), so switched to `Gtk.ColorChooserDialog` with
  `show_editor=True` + `set_rgba()`, seeded from the live entry value.

### Technical Details (picker)

- `generate-arc-colors.sh` now merges `custom-colors.def` (a `name hex` list)
  into its `COLORS` map at load, so picked colours join the full set and are
  reproducible. `--add` sanitizes the name to `[a-z0-9-]`, validates the hex,
  rejects collisions with built-in names, persists the entry, and generates just
  that colour. The static `COLORS` array is never touched.
- The app shells the existing scripts via `Popen` in a daemon thread (no
  `subprocess.call` from callbacks; UI updated through `GLib.idle_add`), streaming
  the generate → `parse_sass.sh` → `render-all.sh <name>` → `install.sh` pipeline
  into a log view. Name suggestions come from sampling several `api.color.pizza`
  word-lists plus `thecolorapi`; a `User-Agent` header is required (color.pizza
  403s the default urllib UA). Screen picking uses `xcolor`; swatch picking uses
  `Gtk.ColorDialog`.
- Build is scoped to the single picked colour: `parse_sass.sh` via
  `THEME_VARIANTS=-<name>`, `render-all.sh <name>`, and `install.sh -t <name>` —
  so picking one colour builds/installs one theme, not the whole set.
- The GUI name-collision check mirrors the generator: built-in names are
  blocked, but an existing custom colour can be re-selected to rebuild it.

### Files Modified

- New: `generate-arc-colors.sh`, `arc-colors-recolor.py`, `arc-colors-scss.py`,
  `render-all.sh`, `README.md`, `CLAUDE.md`, `CHANGELOG.md`
- New: `theme-forge-picker.py`
- Changed: `generate-arc-colors.sh` (`--add` flag + `custom-colors.def` merge),
  `README.md` (picker docs + prerequisites)
