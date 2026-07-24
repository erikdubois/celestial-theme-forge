#!/bin/bash
set -uo pipefail
#####################################################################
# Author : Erik Dubois
# Website : https://kiroproject.be
# DO NOT JUST RUN THIS. EXAMINE AND JUDGE. RUN AT YOUR OWN RISK.
#
# Purpose:
#   Render every per-colour PNG asset (GTK 3/4, GTK 2.0, xfwm4) for all
#   celestial colours, in parallel across colours. Each colour's three
#   render-assets.sh passes run back-to-back; up to JOBS colours render
#   at once. Renders are resumable (existing PNGs are skipped), so the
#   script can be re-run after an interruption.
#
# Why:
#   The full 58-colour asset render is ~50k Inkscape invocations. Running
#   sequentially takes many hours; fanning out across CPU cores brings it
#   down to roughly (total / cores).
#
# Usage:
#   ./render-all.sh                 # all colours, JOBS = nproc
#   JOBS=4 ./render-all.sh          # cap parallelism
#   ./render-all.sh crimson emerald # only the named colours
#   CELESTIAL_DIR=/path ./render-all.sh
#####################################################################
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/celestial-dir.sh"
celestial_require_dir "${SCRIPT_DIR}"
source "${CELESTIAL_DIR}/src/colors.def"

JOBS="${JOBS:-$(nproc)}"
targets=("$@")
[ ${#targets[@]} -eq 0 ] && targets=("${THEME_COLORS[@]}")

export CELESTIAL_DIR
render_one() {
  local c="$1"
  THEME_VARIANTS="-${c}" bash "${CELESTIAL_DIR}/src/gtk/render-assets.sh"     >/dev/null 2>&1
  THEME_VARIANTS="-${c}" bash "${CELESTIAL_DIR}/src/gtk-2.0/render-assets.sh" >/dev/null 2>&1
  THEME_VARIANTS="-${c}" bash "${CELESTIAL_DIR}/src/xfwm4/render-assets.sh"   >/dev/null 2>&1
  echo "  rendered ${c}"
}
export -f render_one

echo "Rendering ${#targets[@]} colour(s) with ${JOBS} parallel jobs into ${CELESTIAL_DIR}..."
printf '%s\n' "${targets[@]}" | xargs -P "$JOBS" -I {} bash -c 'render_one "$@"' _ {}

# Parallel Inkscape sporadically drops a few PNGs under load. A final
# single-threaded pass renders only what's still missing (resumable), which is
# reliable because there's no contention. Cheap when nothing is missing.
echo "Sequential gap-fill pass (guarantees completeness)..."
bash "${CELESTIAL_DIR}/src/gtk/render-assets.sh"     >/dev/null 2>&1
bash "${CELESTIAL_DIR}/src/gtk-2.0/render-assets.sh" >/dev/null 2>&1
bash "${CELESTIAL_DIR}/src/xfwm4/render-assets.sh"   >/dev/null 2>&1

# Plank themes are cheap text templating; regenerate them too.
bash "${CELESTIAL_DIR}/src/plank/render-plank-themes.sh" >/dev/null 2>&1

# KDE Plasma artifacts (color schemes, global themes, desktop themes, aurorae).
# render.sh loops the full colour set from src/colors.def in a single pass and
# derives every colour from the GTK sass palette, so it ignores $targets and
# always renders all colours — cheap next to the Inkscape passes (no PNGs).
echo "Rendering KDE Plasma themes..."
bash "${CELESTIAL_DIR}/src/kde/render.sh"

echo "Done. Now run ${CELESTIAL_DIR}/parse_sass.sh (if needed) and ${CELESTIAL_DIR}/install.sh"
