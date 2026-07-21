#!/bin/bash
#####################################################################
# Author    : Erik Dubois
# Website   : https://kiroproject.be
#####################################################################
#
#   DO NOT JUST RUN THIS. EXAMINE AND JUDGE. RUN AT YOUR OWN RISK.
#
#   Purpose:
#   - Sourced helper (not executed) that resolves CELESTIAL_DIR: the
#     celestial-gtk-theme checkout this forge generates into.
#   - Single source of truth for the lookup order, shared by
#     generate-arc-colors.sh and render-all.sh.
#
#   Why: the forge must run on any Arch box, not only on a machine that
#   happens to have the theme at one hardcoded path.
#####################################################################

CELESTIAL_REPO_URL="${CELESTIAL_REPO_URL:-https://github.com/erikdubois/celestial-gtk-theme.git}"
# Cloned checkouts land in /tmp: throwaway, always writable, no assumptions
# about the user's home layout. Override with CELESTIAL_DIR to keep one.
CELESTIAL_DEFAULT_DIR="${CELESTIAL_DEFAULT_DIR:-/tmp/celestial-gtk-theme}"

celestial_dir_valid() {
    [ -d "$1/src/gtk" ] && [ -f "$1/install.sh" ]
}

# Order: $CELESTIAL_DIR -> forge dir itself (theme+forge in one tree) ->
# sibling of the forge dir -> the /tmp default (may not exist yet).
celestial_resolve_dir() {
    local forge_dir="$1" candidate
    if [ -n "${CELESTIAL_DIR:-}" ]; then
        echo "${CELESTIAL_DIR}"
        return
    fi
    for candidate in "${forge_dir}" \
                     "$(dirname -- "${forge_dir}")/celestial-gtk-theme"; do
        if celestial_dir_valid "${candidate}"; then
            echo "${candidate}"
            return
        fi
    done
    echo "${CELESTIAL_DEFAULT_DIR}"
}

# Resolve + abort with an actionable message when nothing usable is there.
celestial_require_dir() {
    local forge_dir="$1"
    CELESTIAL_DIR="$(celestial_resolve_dir "${forge_dir}")"
    if ! celestial_dir_valid "${CELESTIAL_DIR}"; then
        echo "No celestial-gtk-theme checkout at ${CELESTIAL_DIR}." >&2
        echo "Run: ${forge_dir}/prepare-celestial.py --dir ${CELESTIAL_DIR}" >&2
        echo "(or point CELESTIAL_DIR at an existing checkout)" >&2
        exit 1
    fi
    export CELESTIAL_DIR
}
