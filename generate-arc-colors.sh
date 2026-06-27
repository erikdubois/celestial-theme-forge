#!/bin/bash
set -euo pipefail
#####################################################################
# Author : Erik Dubois
# Website : https://kiroproject.be
# DO NOT JUST RUN THIS. EXAMINE AND JUDGE. RUN AT YOUR OWN RISK.
#
# Purpose:
#   Expand the Celestial GTK theme with the named Arc colour palette
#   (54 colours from kiro-arc-themes). Each new colour is generated as
#   "aliz with a different accent": aliz is the only existing colour
#   built on a neutral dark base, so cloning it and re-accenting yields
#   a clean new variant across every desktop surface.
#
#   The script writes src/colors.def (single source of truth: name,
#   accent, dark-bg), clones aliz's SCSS blocks, entry files, vector
#   sources, window-manager themercs and per-colour assets, and recolours
#   them onto each accent. It is idempotent and re-runnable.
#
# Why:
#   Celestial shipped only 4 colours; this brings it in line with the
#   55-colour kiro-arc collection while reusing celestial's own assets.
#####################################################################
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# Target celestial checkout: use $CELESTIAL_DIR if set, else this script's dir
# when it sits inside the repo, else the default checkout path (theme-forge).
if [ -z "${CELESTIAL_DIR:-}" ]; then
  if [ -d "${SCRIPT_DIR}/src/gtk" ]; then CELESTIAL_DIR="${SCRIPT_DIR}"
  else CELESTIAL_DIR="/home/erik/DATA/celestial-gtk-theme"; fi
fi
SRC="${CELESTIAL_DIR}/src"
RECOLOR="${SCRIPT_DIR}/arc-colors-recolor.py"
SCSS_GEN="${SCRIPT_DIR}/arc-colors-scss.py"
TEMPLATE="aliz"       # neutral-dark source colour we clone
SIBLING="azul"        # clean blue sibling used to isolate accent hexes

# ── Colours ──────────────────────────────────────────────────────────
# Lowercase Arc names (hyphens kept) -> accent hex. Azul is absent (it collides
# with celestial's existing azul, a different hex).
declare -A COLORS=(
  [dawn]="566282"
  [aqua]="66a8cb"            [archlinux-blue]="1793d1"
  [arcolinux-blue]="6790eb"  [azure]="456bff"
  [azure-dodger-blue]="1e9cff" [blood]="cf0808"
  [blueberry]="52428f"       [blue-sky]="7684a8"
  [botticelli]="82a4b3"      [bright-lilac]="cd58ff"
  [carnation]="fe6d88"       [carolina-blue]="6ba4e7"
  [casablanca]="fdb95b"      [cornflower-blue]="3250a7"
  [crimson]="dc143c"         [darkish]="28293d"
  [dodger-blue]="2a8dff"     [dracul]="7e82a0"
  [emerald]="1fa732"         [evopop]="1685a6"
  [fern]="65b058"            [fire]="f68516"
  [froly]="fd7980"           [havelock]="6ba4e7"
  [hibiscus]="d52f61"        [light-blue-grey]="b8a8bc"
  [light-blue-surfn]="94c2e4" [light-salmon]="ffa38d"
  [mandy]="c93648"           [mantis]="6aa847"
  [medium-blue]="4a71c4"     [niagara]="42edcc"
  [nice-blue]="147eb8"       [numix]="ffa726"
  [orchid]="ff7def"          [pale-grey]="e1e3e7"
  [paper]="90a4ae"           [pink]="ce6ca2"
  [polo]="688bc6"            [punch]="c03645"
  [purpley]="8d2dc9"         [red-orange]="fe5100"
  [red-violet]="901265"      [rusty-orange]="e56b1a"
  [sky-blue]="7ec1ff"        [slate-grey]="636a78"
  [smoke]="a1a1a1"           [soft-blue]="5481e5"
  [tacao]="efa369"           [tangerine]="ff9500"
  [tory]="596bb0"            [twilight]="44397d"
  [vampire]="555a69"         [warm-pink]="fd3e84"
)
# Stable display/iteration order (existing 4 first, then new alphabetical).
EXISTING=(sea aliz azul pueril)
NEUTRAL_SCOLOR="#222222"   # all new colours share aliz's neutral dark chrome
# User-picked colours (name hex). In a writable dev checkout this stays in-tree
# (so the committed file keeps working); from a read-only install (/usr/share) it
# falls back to a per-user XDG path.
if [ -w "$SCRIPT_DIR" ]; then
  CUSTOM_DEF="${SCRIPT_DIR}/custom-colors.def"
else
  CUSTOM_DEF="${XDG_CONFIG_HOME:-$HOME/.config}/celestial-theme-forge/custom-colors.def"
fi
CURATED=("${!COLORS[@]}")  # curated names, snapshot before merging customs

# Merge user-picked colours from custom-colors.def into COLORS and (re)compute
# the sorted NEW list. Safe to call repeatedly (idempotent).
merge_custom_colors() {
  local name hex
  if [ -f "$CUSTOM_DEF" ]; then
    while read -r name hex _; do
      case "$name" in ""|\#*) continue;; esac
      [ -n "$hex" ] && COLORS[$name]="${hex#\#}"
    done < "$CUSTOM_DEF"
  fi
  NEW=($(printf '%s\n' "${!COLORS[@]}" | sort))
}
merge_custom_colors

# ── tput colours / logging ───────────────────────────────────────────
if [ -t 1 ]; then
  RED=$(tput setaf 1); GREEN=$(tput setaf 2); YELLOW=$(tput setaf 3)
  BLUE=$(tput setaf 4); CYAN=$(tput setaf 6); RESET=$(tput sgr0)
else
  RED=""; GREEN=""; YELLOW=""; BLUE=""; CYAN=""; RESET=""
fi
log_section() { printf '%s\n############ %s\n%s' "$GREEN" "$*" "$RESET"; echo; }
log_info()    { printf '%s%s%s\n' "$BLUE" "$*" "$RESET"; }
log_warn()    { printf '%s%s%s\n' "$YELLOW" "$*" "$RESET"; }
log_error()   { printf '%s%s%s\n' "$RED" "$*" "$RESET"; }
log_success() { printf '%s%s%s\n' "$GREEN" "$*" "$RESET"; }

on_error() { printf '%sERROR on line %s: %s%s\n' "$RED" "$1" "$2" "$RESET"; sleep 10; }
trap 'on_error "$LINENO" "$BASH_COMMAND"' ERR

# ── helpers ──────────────────────────────────────────────────────────
# Replace the template colour name in a path with the target colour.
retarget() { echo "${1//$TEMPLATE/$2}"; }

# Validate, persist (custom-colors.def) and register a user-picked colour.
# Sets ADDED_NAME to the sanitized name on success; exits non-zero otherwise.
add_custom_color() {
  local raw_name="$1" raw_hex="$2" name hex existing
  name="$(printf '%s' "$raw_name" | tr '[:upper:]' '[:lower:]' | tr ' ' '-' | tr -cd 'a-z0-9-')"
  hex="$(printf '%s' "$raw_hex" | tr '[:upper:]' '[:lower:]')"; hex="${hex#\#}"
  [ -n "$name" ] || { log_error "--add: empty/invalid colour name"; exit 2; }
  case "$hex" in
    [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) ;;
    *) log_error "--add: hex must be 6 hex digits, got '$raw_hex'"; exit 2 ;;
  esac
  # Reject collisions with a stock or curated name; re-adding an existing custom
  # is allowed (it just rebuilds that colour).
  for existing in "${EXISTING[@]}" "${CURATED[@]}"; do
    [ "$existing" = "$name" ] && { log_error "--add: '$name' is a built-in colour name"; exit 3; }
  done
  mkdir -p "$(dirname "$CUSTOM_DEF")"
  [ -f "$CUSTOM_DEF" ] || echo "# User-picked colours (name hex). Appended by theme-forge-picker / --add." > "$CUSTOM_DEF"
  grep -qiE "^${name}[[:space:]]" "$CUSTOM_DEF" || printf '%s %s\n' "$name" "$hex" >> "$CUSTOM_DEF"
  merge_custom_colors
  ADDED_NAME="$name"
  log_info "registered custom colour: $name (#$hex)"
}

# ImageMagick hue param to rotate aliz's accent (#f0544c) to a target hex.
hue_param() {
  python3 - "$1" <<'PY'
import sys, colorsys
def hue(h):
    h=h.lstrip('#'); r,g,b=[int(h[i:i+2],16)/255 for i in (0,2,4)]
    return colorsys.rgb_to_hls(r,g,b)[0]*360
d=(hue(sys.argv[1])-hue('f0544c'))%360
print(round(100+d/1.8,2))
PY
}

# ── generation steps ─────────────────────────────────────────────────
write_colors_def() {
  local def="${SRC}/colors.def" name
  {
    echo "# Auto-generated by generate-arc-colors.sh -- do not edit by hand."
    echo "# Single source of truth for celestial theme colours."
    printf 'THEME_COLORS=(%s %s)\n' "${EXISTING[*]}" "${NEW[*]}"
    echo 'declare -A THEME_PCOLOR=('
    echo '  [sea]="#2eb398" [aliz]="#f0544c" [azul]="#3498db" [pueril]="#97bb72"'
    for name in "${NEW[@]}"; do printf '  [%s]="#%s"\n' "$name" "${COLORS[$name]}"; done
    echo ')'
    echo 'declare -A THEME_SCOLOR=('
    echo '  [sea]="#1b2224" [aliz]="#222222" [azul]="#1b1d24" [pueril]="#222222"'
    for name in "${NEW[@]}"; do printf '  [%s]="%s"\n' "$name" "$NEUTRAL_SCOLOR"; done
    echo ')'
  } > "$def"
  log_info "wrote ${def#"$SCRIPT_DIR"/} (${#NEW[@]} new colours)"
}

gen_scss_blocks() {
  local tsv name
  tsv="$(mktemp)"
  for name in "${NEW[@]}"; do printf '%s\t%s\n' "$name" "${COLORS[$name]}"; done > "$tsv"
  python3 "$SCSS_GEN" "$tsv" \
    "${SRC}/gtk/sass/_colors.scss" \
    "${SRC}/cinnamon/sass/_colors.scss" \
    "${SRC}/gnome-shell/sass/40.0/_colors.scss" \
    "${SRC}/gnome-shell/sass/3.28/_colors.scss"
  rm -f "$tsv"
  log_info "cloned SCSS \$color blocks for ${#NEW[@]} colours"
}

# Clone every aliz entry .scss, swapping the \$color value.
gen_entries() {
  local c="$1" f out
  while IFS= read -r f; do
    out="$(retarget "$f" "$c")"
    sed "s/\$color: \"$TEMPLATE\"/\$color: \"$c\"/" "$f" > "$out"
  done < <(find "$SRC" -name "*${TEMPLATE}*.scss")
}

# Clone + recolour the SVG/text/xml sources for one colour.
gen_assets() {
  local c="$1" hex="#${COLORS[$1]}" f out
  # GTK 3/4 asset sheet
  cp "${SRC}/gtk/assets-${TEMPLATE}.svg" "${SRC}/gtk/assets-${c}.svg"
  # GTK 2.0 asset sheets + gtkrc text
  for f in "${SRC}/gtk-2.0/assets-${TEMPLATE}.svg" "${SRC}/gtk-2.0/assets-${TEMPLATE}-dark.svg" \
           "${SRC}/gtk-2.0/gtkrc-${TEMPLATE}" "${SRC}/gtk-2.0/gtkrc-${TEMPLATE}-dark" "${SRC}/gtk-2.0/gtkrc-${TEMPLATE}-light"; do
    cp "$f" "$(retarget "$f" "$c")"
  done
  # xfwm4 asset sheets + themerc
  for f in "${SRC}/xfwm4/assets-${TEMPLATE}.svg" "${SRC}/xfwm4/assets-${TEMPLATE}-light.svg" \
           "${SRC}/xfwm4/assets-${TEMPLATE}-dark.svg" "${SRC}/xfwm4/themerc-${TEMPLATE}"; do
    cp "$f" "$(retarget "$f" "$c")"
  done
  # Cinnamon asset dir (used directly) + gnome-shell theme-assets
  cp -r "${SRC}/cinnamon/assets-${TEMPLATE}" "${SRC}/cinnamon/assets-${c}"
  while IFS= read -r f; do cp "$f" "$(retarget "$f" "$c")"; done \
    < <(find "${SRC}/gnome-shell/theme-assets" -name "*${TEMPLATE}*.svg")
  # Metacity, openbox, labwc themercs (+ labwc png buttons)
  cp "${SRC}/metacity-1/metacity-theme-1-${TEMPLATE}.xml" "${SRC}/metacity-1/metacity-theme-1-${c}.xml"
  for f in "${SRC}/openbox-3/themerc-${TEMPLATE}" "${SRC}/openbox-3/themerc-${TEMPLATE}-dark" \
           "${SRC}/labwc/themerc-${TEMPLATE}" "${SRC}/labwc/themerc-${TEMPLATE}-dark" "${SRC}/labwc/themerc-${TEMPLATE}-light"; do
    cp "$f" "$(retarget "$f" "$c")"
  done
  cp -r "${SRC}/labwc/assets-${TEMPLATE}" "${SRC}/labwc/assets-${c}"
  cp -r "${SRC}/labwc/assets-${TEMPLATE}-light" "${SRC}/labwc/assets-${c}-light"
  # Optional extra app themes (cheap hex configs)
  for f in "${SRC}/extra/copyq/celestial-${TEMPLATE}-dark.ini" "${SRC}/extra/copyq/celestial-${TEMPLATE}-light.ini" \
           "${SRC}/extra/halloy/celestial-${TEMPLATE}.toml" "${SRC}/extra/zed/celestial-${TEMPLATE}.json"; do
    [ -e "$f" ] && cp "$f" "$(retarget "$f" "$c")"
  done

  # Precise recolour (SVG/XML/text): pass each azul sibling so only accent hexes move.
  python3 "$RECOLOR" "$hex" \
    "${SRC}/gtk/assets-${SIBLING}.svg"                 "${SRC}/gtk/assets-${c}.svg" \
    "${SRC}/gtk-2.0/assets-${SIBLING}.svg"             "${SRC}/gtk-2.0/assets-${c}.svg" \
    "${SRC}/gtk-2.0/assets-${SIBLING}-dark.svg"        "${SRC}/gtk-2.0/assets-${c}-dark.svg" \
    "${SRC}/xfwm4/assets-${SIBLING}.svg"               "${SRC}/xfwm4/assets-${c}.svg" \
    "${SRC}/xfwm4/assets-${SIBLING}-light.svg"         "${SRC}/xfwm4/assets-${c}-light.svg" \
    "${SRC}/xfwm4/assets-${SIBLING}-dark.svg"          "${SRC}/xfwm4/assets-${c}-dark.svg" \
    "${SRC}/cinnamon/assets-${SIBLING}"                "${SRC}/cinnamon/assets-${c}" \
    "${SRC}/gnome-shell/theme-assets/checkbox-${SIBLING}.svg"      "${SRC}/gnome-shell/theme-assets/checkbox-${c}.svg" \
    "${SRC}/gnome-shell/theme-assets/more-results-${SIBLING}.svg"  "${SRC}/gnome-shell/theme-assets/more-results-${c}.svg" \
    "${SRC}/gnome-shell/theme-assets/toggle-on-${SIBLING}.svg"     "${SRC}/gnome-shell/theme-assets/toggle-on-${c}.svg" \
    "${SRC}/gnome-shell/theme-assets/toggle-on-${SIBLING}-dark.svg" "${SRC}/gnome-shell/theme-assets/toggle-on-${c}-dark.svg" \
    "${SRC}/metacity-1/metacity-theme-1-${SIBLING}.xml" "${SRC}/metacity-1/metacity-theme-1-${c}.xml" \
    >/dev/null
  # Hex-bearing text configs share azul siblings too.
  recolor_text "$c" "$hex"

  # PNG-only assets (no SVG source): hue-rotate aliz's onto the target hue.
  png_recolor "$c" "$hex"
}

# Recolour gtkrc/themerc/extra text by mapping the literal accent (azul sibling).
recolor_text() {
  local c="$1" hex="$2" f
  python3 "$RECOLOR" "$hex" \
    "${SRC}/gtk-2.0/gtkrc-${SIBLING}"            "${SRC}/gtk-2.0/gtkrc-${c}" \
    "${SRC}/gtk-2.0/gtkrc-${SIBLING}-dark"       "${SRC}/gtk-2.0/gtkrc-${c}-dark" \
    "${SRC}/gtk-2.0/gtkrc-${SIBLING}-light"      "${SRC}/gtk-2.0/gtkrc-${c}-light" \
    "${SRC}/openbox-3/themerc-${SIBLING}"        "${SRC}/openbox-3/themerc-${c}" \
    "${SRC}/openbox-3/themerc-${SIBLING}-dark"   "${SRC}/openbox-3/themerc-${c}-dark" \
    "${SRC}/labwc/themerc-${SIBLING}"            "${SRC}/labwc/themerc-${c}" \
    "${SRC}/labwc/themerc-${SIBLING}-dark"       "${SRC}/labwc/themerc-${c}-dark" \
    "${SRC}/labwc/themerc-${SIBLING}-light"      "${SRC}/labwc/themerc-${c}-light" \
    >/dev/null
  for f in "extra/copyq/celestial-${c}-dark.ini:extra/copyq/celestial-${SIBLING}-dark.ini" \
           "extra/copyq/celestial-${c}-light.ini:extra/copyq/celestial-${SIBLING}-light.ini" \
           "extra/halloy/celestial-${c}.toml:extra/halloy/celestial-${SIBLING}.toml" \
           "extra/zed/celestial-${c}.json:extra/zed/celestial-${SIBLING}.json"; do
    local tgt="${SRC}/${f%%:*}" sib="${SRC}/${f##*:}"
    [ -e "$tgt" ] && [ -e "$sib" ] && python3 "$RECOLOR" "$hex" "$sib" "$tgt" >/dev/null
  done
}

# Hue-rotate aliz PNG previews/buttons (no vector source) onto the target hue.
png_recolor() {
  local c="$1" hex="$2" hp f out
  hp="$(hue_param "$hex")"
  for f in "${SRC}/gtk/thumbnail-${TEMPLATE}.png" "${SRC}/gtk/thumbnail-${TEMPLATE}-dark.png" \
           "${SRC}/cinnamon/thumbnail-${TEMPLATE}.png" "${SRC}/cinnamon/thumbnail-${TEMPLATE}-dark.png"; do
    [ -e "$f" ] && magick "$f" -modulate 100,100,"$hp" "$(retarget "$f" "$c")"
  done
  for f in "${SRC}/labwc/assets-${c}"/*.png "${SRC}/labwc/assets-${c}-light"/*.png; do
    [ -e "$f" ] && magick "$f" -modulate 100,100,"$hp" "$f"
  done
}

main() {
  local targets
  if [ "${1:-}" = "--add" ]; then
    add_custom_color "${2:-}" "${3:-}"   # validates, persists, refreshes COLORS/NEW
    targets=("$ADDED_NAME")
  else
    targets=("$@")
    [ ${#targets[@]} -eq 0 ] && targets=("${NEW[@]}")
  fi
  log_section "Generating ${#targets[@]} celestial colour(s)"
  write_colors_def
  # SCSS blocks are ALWAYS (re)generated for the full colour set — the helper
  # strips and re-inserts every generated block, so a subset run must not drop
  # the others. Only entries/assets below are restricted to the requested set.
  gen_scss_blocks
  local c i=0
  for c in "${targets[@]}"; do
    [ -n "${COLORS[$c]+x}" ] || { log_error "unknown colour: $c"; continue; }
    i=$((i + 1))
    log_info "[$i/${#targets[@]}] $c (#${COLORS[$c]})"
    gen_entries "$c"
    gen_assets "$c"
  done
  log_success "$(basename "$0") done -- run parse_sass.sh + src/*/render-assets.sh to build, then install.sh"
}

main "$@"
