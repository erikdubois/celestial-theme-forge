# Changelog

## 2026.07.21

### What Changed

- Picker: new "4. Kiro: GTK_THEME override" section, shown only on Kiro. Kiro ships
  `GTK_THEME="Arc-Dawn-Dark"` in `/etc/environment`; while active it overrides every
  GTK theme, so a freshly built celestial theme silently does nothing. One button
  toggles the `#` comment on that line, a second opens the file in `nano` for a
  manual edit.

### Technical Details

- Kiro detection is `IMAGE_ID=kiro` in `/etc/os-release` (`ID` is still `arch`).
  The section is also hidden if no `GTK_THEME` line exists at all.
- Toggle runs `pkexec /usr/bin/sed -i` (a polkit agent is part of every Kiro
  session) in a daemon thread — never blocking the GTK callback. The button label
  and hint are derived from a re-read of `/etc/environment` after each action,
  including after the nano editor exits, so they can't drift from the file.
- Nano opens in `$TERMINAL`, else the first of a known terminal list found on
  PATH; `sudo nano` rather than `pkexec nano` because nano needs a TTY.
- The log notes that a re-login is required — `/etc/environment` is read at PAM
  session start, so nothing changes live.

### Files Modified

- `theme-forge-picker.py`

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
- Picker now shows a "Recent" strip of 10 colour slots (click a filled swatch to
  restore it). Always shows all 10 squares — empty ones as faint outlined
  placeholders that fill left→right as you pick colours. A colour is recorded
  when you exit the picker (Choose… or Pick from screen), deduped; the 11th pick
  drops the oldest (leftmost). Persisted in
  `$XDG_CONFIG_HOME/celestial-theme-forge/recent-colors`.
- Added `build.sh`: one-shot shipper that keeps this folder clean and publishes
  the package to `nemesis_repo`. Building in place left `src/`, `pkg/`, a nested
  `celestial-theme-forge/` git clone and `*.pkg.tar.zst` cluttering the repo;
  these are now wiped up front and gitignored.

### Technical Details (build.sh)

- Pipeline: wipe makepkg leftovers → bump PKGBUILD (CalVer `pkgver`, auto
  `pkgrel`) → `up.sh` (push source to GitHub) → build in `/tmp` via
  `makechrootpkg` → copy `.pkg.tar.zst` into `nemesis_repo/x86_64/` →
  `nemesis_repo/up.sh` (repo-add + push live).
- Cleanup + `.gitignore` run **before** `up.sh`, since `up.sh` does
  `git add --all` — otherwise the nested clone and pkg get pushed to GitHub.
- The source push is required because the PKGBUILD uses `source=git+<github>`:
  `makepkg` pulls the payload from GitHub, so an un-pushed change ships stale.
  This is why this self-contained repo's `build.sh` also does the source push,
  unlike the canonical split `flow-*` pipeline.

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
- New: `theme-forge-picker.py`, `build.sh`
- Changed: `generate-arc-colors.sh` (`--add` flag + `custom-colors.def` merge),
  `README.md` (picker docs + prerequisites), `.gitignore` (makepkg artifacts)
