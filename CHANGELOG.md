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

---

- Made the forge run on any Arch system instead of assuming a theme checkout at
  one hardcoded path. Added `prepare-celestial.py`, which clones
  celestial-gtk-theme and patches it to be `colors.def`-driven, so a fresh
  machine goes clone → build with no manual preparation. The picker gained a
  **Get theme source** button for the same thing.

### Technical Details

- `celestial-dir.sh` is now the single definition of the lookup order
  (`$CELESTIAL_DIR` → this tree → sibling `../celestial-gtk-theme` →
  `/tmp/celestial-gtk-theme`), sourced by `generate-arc-colors.sh` and
  `render-all.sh`; `theme-forge-picker.py` mirrors it in Python. The sibling
  step is what keeps an existing `DATA/celestial-gtk-theme` working without a
  username appearing anywhere. `celestial_require_dir` aborts with the exact
  `prepare-celestial.py` command to run rather than failing deep in a render.
- Cloned checkouts default to `/tmp`: always writable, no assumption about the
  home layout. Ephemeral, hence `CELESTIAL_DIR` for a checkout worth keeping.
- Upstream celestial hardcodes the four stock colour names in `install.sh`,
  `parse_sass.sh`, three `render-assets.sh` and `render-plank-themes.sh` — the
  edits making them data-driven had only ever existed as uncommitted local
  changes. `prepare-celestial.py` now carries them as exact-string anchor →
  replacement pairs, skips a patch whose replacement is already present, and
  `sys.exit`s if an anchor is missing so an upstream change surfaces instead of
  producing a half-patched tree. The plank loop patch carries a following line
  as context because `PLANK_EXTEND` introduces an identical loop header.
- Verified against a fresh clone: five of the six patched files come out
  byte-identical to the hand-patched working checkout (`install.sh` differs only
  in upstream's version string, 1.3.5 vs 1.3.3), the run is idempotent, and
  generate → `parse_sass.sh` compiles a colour in the /tmp clone.
- Picker: "Create theme" stays insensitive while no valid checkout is resolved.
- `git` moved from `makedepends` to `depends` — it is now needed at runtime.

### Files Modified

- `celestial-dir.sh` (new), `prepare-celestial.py` (new)
- `generate-arc-colors.sh`, `render-all.sh`, `theme-forge-picker.py`
- `README.md`, `CLAUDE.md`, `PKGBUILD`

---

- Picker: header row with a title, a pink **♥ Support** button and **Quit**,
  matching the other Kiro tweak tools. Support opens a dialog with the five
  funding channels.

### Technical Details

- `FUNDING` and the `.support-button` CSS are copied from
  `alacritty-tweak-tool`'s header so the tools stay visually consistent; the
  list must track kiro-website `.github/FUNDING.yml`. The picker has no CSS
  file, so the rules load from an inline `Gtk.CssProvider` in `do_activate`.
- Fixed two defects in the theme-source button found before shipping:
  `prepare-celestial.py` was not executable (dev checkout only — the package
  installs it 755), so the picker's direct `Popen` of it would have raised
  `PermissionError`. It is now invoked via `sys.executable`, is `chmod +x`, and
  `_source_worker` guards `Popen` with `try/except OSError` so a failed launch
  can no longer strand `_busy=True` and disable the buttons permanently.
- Verified by driving the real handlers (not just launching): with a missing
  checkout the button shows and Create is blocked; clicking it clones + patches
  into `/tmp/ctf-verify`, hides the button, updates the label and enables
  Create; the Support dialog opens as a toplevel titled "Support Kiro".

### Files Modified

- `theme-forge-picker.py`, `prepare-celestial.py` (mode 755)

---

- Picker: **Pick from screen** now selects its tool per session — `xcolor` on
  X11, `hyprpicker` on Wayland — instead of always shelling out to `xcolor`.

### Technical Details

- The old gate was only `find_program_in_path("xcolor")`, a PATH check with no
  notion of the session, so on Wayland the button stayed enabled and failed
  quietly two ways: with XWayland up, xcolor grabbed XWayland's root window,
  which holds no composited output, and returned a bogus colour (usually black)
  with exit 0 — the hex passed `HEX_RE` and was accepted as a real pick; with no
  XWayland it exited non-zero and the empty stdout made it a silent no-op.
- `eyedropper_argv()` picks the tool off `$WAYLAND_DISPLAY`. hyprpicker runs as
  `-f hex -l -b -q`; `-b` matters because its default "fancy" output wraps the
  hex in ANSI colour escapes, which `HEX_RE` would reject.
- The button is now disabled at construction with a tooltip naming the missing
  tool when the session's picker is absent, rather than looking usable. The
  runtime check stays for the case where it disappears while the app is open.
- hyprpicker is wlroots-only, so this covers the Kiro Wayland TWM editions but
  not GNOME/KDE; the compositor-agnostic option remains the
  `org.freedesktop.portal.Screenshot.PickColor` portal call.
- Verified: tool selection flips correctly on `$WAYLAND_DISPLAY`; hyprpicker on
  an X11 session fails cleanly (exit 1, empty stdout → no-op, same as cancel);
  and the Wayland branch driven end-to-end against a stub picker fills the hex
  entry, lowercases the value and records it in Recent.

### Files Modified

- `theme-forge-picker.py`, `README.md`, `PKGBUILD`

---

- Fixed **Pick from screen** doing nothing on Hyprland: the loupe appeared and a
  colour could be picked, but it never reached the swatch.

### Technical Details

- Cause was the `-q` flag added with the Wayland support. hyprpicker emits the
  picked colour through its own logger at level `NONE`, and `Debug::log` opens
  with `if (quiet && level != ERR && level != CRIT) return;` — so `--quiet`
  suppresses the result itself. It exited 0 with empty stdout, `HEX_RE` rejected
  the empty string, and `_eyedropper_worker` returned without touching the UI:
  the same silent no-op path as a cancelled pick.
- Dropping `-q` alone is not enough — without it hyprpicker writes `[WARN]`
  lines (unsupported `wp_viewporter` / `wp_fractional_scale_v1`) to stdout, and
  the old code stripped the whole of stdout and matched that. `extract_hex()`
  now scans the lines in reverse for the first that matches `HEX_RE`, so log
  noise before the result is ignored and a run with no result still yields ''.
- `-b` is kept although hyprpicker already disables fancy output when stdout is
  not a TTY; it makes the intent explicit and covers a TTY-attached run, where
  the colour would otherwise be wrapped in ANSI escapes that `HEX_RE` rejects.
- Verified: `extract_hex` over five outputs (bare hex, warning + hex, warnings
  only, empty, critical-only), and the Wayland path end-to-end against a stub
  reproducing hyprpicker's warning-then-hex output.

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
