#!/usr/bin/env python3
"""Clone celestial-gtk-theme if absent and patch it to be colors.def-driven."""
import argparse
import os
import shutil
import subprocess
import sys

REPO_URL = os.environ.get("CELESTIAL_REPO_URL",
                          "https://github.com/erikdubois/celestial-gtk-theme.git")
DEFAULT_DIR = os.environ.get("CELESTIAL_DIR") or "/tmp/celestial-gtk-theme"

# Upstream ships four hardcoded colour names in six scripts. The forge needs
# them driven by src/colors.def instead. Each patch is (anchor, replacement);
# a patch whose anchor is gone is either already applied (marker present) or a
# sign that upstream moved — the latter aborts rather than half-patching.
SOURCE_COLORS_DEF = 'source "${SCRIPT_DIR}/../colors.def"'

RENDER_PROLOGUE = """INKSCAPE="/usr/bin/inkscape"
OPTIPNG="$(command -v optipng || true)"   # optional: only shrinks files
optimize() { [ -n "$OPTIPNG" ] && "$OPTIPNG" -o7 --quiet "$1" || true; }

""" + SOURCE_COLORS_DEF + """
INDEX="assets.txt"

_COLORS=("${THEME_COLORS[@]/#/-}")
if [[ -n "${THEME_VARIANTS:-}" ]]; then IFS=', ' read -r -a _COLORS <<< "${THEME_VARIANTS}"; fi
"""

RENDER_PROLOGUE_ANCHOR = """INKSCAPE="/usr/bin/inkscape"
OPTIPNG="/usr/bin/optipng"

INDEX="assets.txt"
"""

PLANK_EXTEND = '''
# Extend with the generated Arc colours (src/colors.def). New colours share
# aliz's neutral #222222 chrome; only the accent differs.
''' + SOURCE_COLORS_DEF + '''
hex2rgb() { printf '%d %d %d' "0x${1:1:2}" "0x${1:3:2}" "0x${1:5:2}"; }
cap() { local s="${1//-/ }"; echo "${s^}" | sed 's/ /-/g'; }
for theme in "${THEME_COLORS[@]}"; do
    [ -n "${COLORS[$theme]+x}" ] && continue
    hex="${THEME_PCOLOR[$theme]}"
    read -r R G B <<< "$(hex2rgb "$hex")"
    COLORS["$theme"]="$R $G $B $hex"
    THEME_NAMES["$theme"]="$(cap "$theme")"
    DARK_BGS["$theme"]="34;;34;;34"
    DARK_OUTER_STROKES["$theme"]="26;;26;;26;;215"
done

generate_theme() {'''

INSTALL_CASE_ANCHOR = """          sea)
            themes+=("${THEME_VARIANTS[0]}")
            shift 1
            ;;
          aliz)
            themes+=("${THEME_VARIANTS[1]}")
            shift 1
            ;;
          azul)
            themes+=("${THEME_VARIANTS[2]}")
            shift 1
            ;;
          pueril)
            themes+=("${THEME_VARIANTS[3]}")
            shift 1
            ;;
          -*)
            break
            ;;
          *)
            echo "ERROR: Unrecognized theme variant '$1'."
            echo "Try '$0 --help' for more information."
            exit 1
            ;;"""

INSTALL_CASE = """          -*)
            break
            ;;
          *)
            if [[ " ${THEME_COLORS[*]} " == *" ${theme} "* ]]; then
              themes+=("-${theme}")
              shift 1
            else
              echo "ERROR: Unrecognized theme variant '${theme}'."
              echo "Try '$0 --help' for more information."
              exit 1
            fi
            ;;"""

INSTALL_XML_ANCHOR = """  # Set theme-specific colors
  local pcolor="#000000"
  local scolor="#000000"

  case "${theme_name}" in
    sea)
      pcolor="#2eb398"
      scolor="#1b2224"
      ;;
    azul)
      pcolor="#3498db"
      scolor="#1b1d24"
      ;;
    aliz)
      pcolor="#f0544c"
      scolor="#222222"
      ;;
    pueril)
      pcolor="#97bb72"
      scolor="#222222"
      ;;
  esac"""

INSTALL_XML = """  # Set theme-specific colors (from src/colors.def)
  local pcolor="${THEME_PCOLOR[${theme_name}]:-#000000}"
  local scolor="${THEME_SCOLOR[${theme_name}]:-#000000}\""""

# src/kde/render.sh renders every KDE Plasma artifact (color schemes, global
# themes, desktop themes, aurorae) by looping four hardcoded themes and deriving
# all colours from the GTK sass palette. Make the loop colors.def-driven; add a
# button-colour fallback for generated colours (the accent-only recolour keeps
# their neutral chrome greys, so only PRESSBG — the accent — varies); omit the
# wallpaper section for colours with no wallpaper package; and skip the heavy
# 1920x1080 fullscreen preview JPEG (the KCM falls back to the grid thumbnail).
KDE_LOOP_ANCHOR = "for theme in sea aliz azul pueril; do"
KDE_LOOP = ('source "${REPO_DIR}/src/colors.def"\n'
            'for theme in "${THEME_COLORS[@]}"; do')

KDE_BUTTON_ANCHOR = """    *)
      echo "ERROR: no button colors for '${key}'."
      exit 1
      ;;"""
KDE_BUTTON = """    *)
      # Generated (aliz-derived) colours: the accent-only recolour preserves the
      # neutral chrome greys, so only PRESSBG (the accent) varies per colour.
      local _bt="${key%%|*}" _bm="${key##*|}"
      case "${_bm}" in
        light) CLOSEGLYPH="#4d4d4d"; GLYPH="#4d4d4d"; HOVERBG="#565656"; HOVEROP=".25"; HOVERGLYPH="#4c4c4c" ;;
        *)     CLOSEGLYPH="#c3c3c3"; GLYPH="#adadad"; HOVERBG="#838383"; HOVEROP=".45"; HOVERGLYPH="#b0b0b0" ;;
      esac
      PRESSBG="${THEME_PCOLOR[${_bt}]:-#ffffff}"
      ;;"""

KDE_WALLPAPER_ANCHOR = """      pueril) wallpaper="Celestial-Pueril-Bamboo" ;;
    esac"""
KDE_WALLPAPER = """      pueril) wallpaper="Celestial-Pueril-Bamboo" ;;
      *) wallpaper="" ;;
    esac"""

KDE_DEFAULTS_ANCHOR = """[ksplashrc][KSplash]
Theme=${ID_PREFIX}${scheme_id}

[Wallpaper]
Image=${wallpaper}
EOF
}"""
KDE_DEFAULTS = """[ksplashrc][KSplash]
Theme=${ID_PREFIX}${scheme_id}
EOF

  # Wallpaper packages exist only for the stock colours; generated colours omit
  # the section so applying the global theme keeps the current wallpaper.
  if [[ -n "${wallpaper}" ]]; then
    cat >> "${out}" << EOF

[Wallpaper]
Image=${wallpaper}
EOF
  fi
}"""

KDE_PREVIEW_ANCHOR = '''  # Fullscreen preview (the KCM's "Show Preview"); the package structure expects
  # this exact JPEG path, so rsvg to PNG then convert to JPEG
  rsvg-convert -w 1920 -h 1080 "${TMP_DIR}/preview.svg" -o "${TMP_DIR}/fullscreen.png" || exit 1
  "${JPEG_CONVERT[@]}" "${TMP_DIR}/fullscreen.png" -quality 88 "${dir}/fullscreenpreview.jpg" || exit 1'''
KDE_PREVIEW = '''  # Fullscreen preview intentionally skipped (celestial-theme-forge): across the
  # 58x3 variants the 1920x1080 JPEGs dominate on-disk size, and the KCM falls
  # back to the grid thumbnail (preview.png) when the fullscreen JPEG is absent.'''

# A dark accent's WALL2 = darken(accent, 28%) can clamp to pure black, which
# sassc emits as the CSS keyword "black" rather than "#000000"; the original
# extraction regex only matched "#hex" and dropped it, aborting on the resulting
# {{WALL2}}. Widen the value capture to any non-";" token (SVG/QML/magick all
# accept colour keywords). Only the stock four accents dodged this.
KDE_PREVIEW_RE_ANCHOR = (
    r'''sed -n 's/^ *\([A-Z0-9]\+\): \(#[0-9a-fA-F]*\);$/\1=\2/p' "${TMP_DIR}/preview.css"''')
KDE_PREVIEW_RE = (
    r'''sed -n 's/^ *\([A-Z0-9]\+\): \([^;]*\);$/\1=\2/p' "${TMP_DIR}/preview.css"''')

# file -> list of (anchor, replacement)
PATCHES = {
    "parse_sass.sh": [(
        "_THEME_VARIANTS=('-sea' '-aliz' '-azul' '-pueril')",
        'SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"\n'
        'source "${SCRIPT_DIR}/src/colors.def"\n'
        '_THEME_VARIANTS=("${THEME_COLORS[@]/#/-}")',
    )],
    "install.sh": [
        ("THEME_VARIANTS=('-sea' '-aliz' '-azul' '-pueril')",
         'source "${SRC_DIR}/colors.def"\nTHEME_VARIANTS=("${THEME_COLORS[@]/#/-}")'),
        ('"-t, --theme VARIANTS" "Theme variant [sea|aliz|azul|pueril] (Default: All)"',
         '"-t, --theme VARIANTS" "Theme variant (names in src/colors.def; Default: All)"'),
        (INSTALL_CASE_ANCHOR, INSTALL_CASE),
        (INSTALL_XML_ANCHOR, INSTALL_XML),
    ],
    "src/gtk/render-assets.sh": [
        (RENDER_PROLOGUE_ANCHOR, RENDER_PROLOGUE),
        ("for color in '-aliz' '-azul' '-sea' '-pueril'; do\n"
         '  ASSETS_DIR="assets${color}"\n'
         '  SRC_FILE="assets${color}.svg"\n\n'
         '  [ -d "$ASSETS_DIR" ] && rm -rf "$ASSETS_DIR" && mkdir -p "$ASSETS_DIR"',
         'for color in "${_COLORS[@]}"; do\n'
         '  ASSETS_DIR="assets${color}"\n'
         '  SRC_FILE="assets${color}.svg"\n'
         '  [ -f "$SRC_FILE" ] || { echo "skip ${color}: no $SRC_FILE"; continue; }\n\n'
         '  mkdir -p "$ASSETS_DIR"'),
        ('$OPTIPNG -o7 --quiet "$ASSETS_DIR/$i.png"', 'optimize "$ASSETS_DIR/$i.png"'),
        ('$OPTIPNG -o7 --quiet "$ASSETS_DIR/$i@2.png"', 'optimize "$ASSETS_DIR/$i@2.png"'),
    ],
    "src/gtk-2.0/render-assets.sh": [
        (RENDER_PROLOGUE_ANCHOR, RENDER_PROLOGUE),
        ("  for color in '-sea' '-aliz' '-azul' '-pueril'; do\n\n"
         '    ASSETS_DIR="assets${color}${variant}"\n'
         '    SRC_FILE="assets${color}${variant}.svg"',
         '  for color in "${_COLORS[@]}"; do\n\n'
         '    ASSETS_DIR="assets${color}${variant}"\n'
         '    SRC_FILE="assets${color}${variant}.svg"\n'
         '    [ -f "$SRC_FILE" ] || { echo "skip ${color}${variant}: no $SRC_FILE"; continue; }'),
        ('--export-filename="$ASSETS_DIR/$i.png" "$SRC_FILE" >/dev/null \\\n'
         '        && $OPTIPNG -o7 --quiet "$ASSETS_DIR/$i.png"',
         '--export-filename="$ASSETS_DIR/$i.png" "$SRC_FILE" >/dev/null\n'
         '        optimize "$ASSETS_DIR/$i.png"'),
    ],
    "src/xfwm4/render-assets.sh": [
        (RENDER_PROLOGUE_ANCHOR, RENDER_PROLOGUE),
        ("  for color in '-sea' '-aliz' '-azul' '-pueril'; do\n\n"
         '    ASSETS_DIR="assets${color}${variant}"\n'
         '    HD_ASSETS_DIR="assets${color}-hdpi${variant}"\n'
         '    XHD_ASSETS_DIR="assets${color}-xhdpi${variant}"\n'
         '    SRC_FILE="assets${color}${variant}.svg"',
         '  for color in "${_COLORS[@]}"; do\n\n'
         '    ASSETS_DIR="assets${color}${variant}"\n'
         '    HD_ASSETS_DIR="assets${color}-hdpi${variant}"\n'
         '    XHD_ASSETS_DIR="assets${color}-xhdpi${variant}"\n'
         '    SRC_FILE="assets${color}${variant}.svg"\n'
         '    [ -f "$SRC_FILE" ] || { echo "skip ${color}${variant}: no $SRC_FILE"; continue; }'),
        ('--export-filename="$ASSETS_DIR/$i.png" "$SRC_FILE" >/dev/null \\\n'
         '        && $OPTIPNG -o7 --quiet "$ASSETS_DIR/$i.png"',
         '--export-filename="$ASSETS_DIR/$i.png" "$SRC_FILE" >/dev/null\n'
         '        optimize "$ASSETS_DIR/$i.png"'),
        ('--export-filename="$HD_ASSETS_DIR/$i.png" "$SRC_FILE" >/dev/null \\\n'
         '        && $OPTIPNG -o7 --quiet "$HD_ASSETS_DIR/$i.png"',
         '--export-filename="$HD_ASSETS_DIR/$i.png" "$SRC_FILE" >/dev/null\n'
         '        optimize "$HD_ASSETS_DIR/$i.png"'),
        ('--export-filename="$XHD_ASSETS_DIR/$i.png" "$SRC_FILE" >/dev/null \\\n'
         '        && $OPTIPNG -o7 --quiet "$XHD_ASSETS_DIR/$i.png"',
         '--export-filename="$XHD_ASSETS_DIR/$i.png" "$SRC_FILE" >/dev/null\n'
         '        optimize "$XHD_ASSETS_DIR/$i.png"'),
    ],
    "src/plank/render-plank-themes.sh": [
        ("\ngenerate_theme() {", PLANK_EXTEND),
        # Context-carrying anchor: PLANK_EXTEND already introduces a
        # `for theme in "${THEME_COLORS[@]}"` line, so the final render loop
        # needs the following line to tell the two apart.
        ('for theme in sea aliz azul pueril; do\n    generate_theme',
         'for theme in "${THEME_COLORS[@]}"; do\n    generate_theme'),
    ],
    "src/kde/render.sh": [
        (KDE_LOOP_ANCHOR, KDE_LOOP),
        (KDE_BUTTON_ANCHOR, KDE_BUTTON),
        (KDE_WALLPAPER_ANCHOR, KDE_WALLPAPER),
        (KDE_DEFAULTS_ANCHOR, KDE_DEFAULTS),
        (KDE_PREVIEW_ANCHOR, KDE_PREVIEW),
        (KDE_PREVIEW_RE_ANCHOR, KDE_PREVIEW_RE),
    ],
}


def log(msg):
    print(msg, flush=True)


def clone(dest):
    log(f"Cloning {REPO_URL} into {dest}")
    parent = os.path.dirname(os.path.abspath(dest)) or "."
    os.makedirs(parent, exist_ok=True)
    subprocess.run(["git", "clone", "--depth", "1", REPO_URL, dest], check=True)


def patch_file(root, rel, patches):
    """Apply this file's patches; return True if anything changed."""
    path = os.path.join(root, rel)
    text = open(path, encoding="utf-8").read()
    original = text
    for anchor, replacement in patches:
        if replacement in text:
            continue
        if anchor not in text:
            sys.exit(f"{rel}: expected upstream code not found — upstream changed?\n"
                     f"  looking for: {anchor.splitlines()[0]}")
        text = text.replace(anchor, replacement)
    if text == original:
        return False
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", default=DEFAULT_DIR,
                    help=f"celestial checkout to prepare (default: {DEFAULT_DIR})")
    ap.add_argument("--force", action="store_true",
                    help="delete an existing checkout and clone it again")
    args = ap.parse_args()
    dest = args.dir

    if args.force and os.path.isdir(dest):
        log(f"Removing {dest}")
        shutil.rmtree(dest)
    if not os.path.isdir(os.path.join(dest, "src", "gtk")):
        clone(dest)

    changed = [rel for rel, patches in PATCHES.items() if patch_file(dest, rel, patches)]
    if changed:
        log("Patched to be colors.def-driven: " + ", ".join(changed))
    else:
        log("Already colors.def-driven — nothing to patch.")
    log(f"Ready: {dest}")


if __name__ == "__main__":
    main()
