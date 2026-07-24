#!/bin/bash
set -euo pipefail
#####################################################################
# Author  : Erik Dubois
# Website : https://kiroproject.be
#
#   DO NOT JUST RUN THIS. EXAMINE AND JUDGE. RUN AT YOUR OWN RISK.
#
#   Purpose:
#   - Create ONLY the KDE Plasma output for celestial-themes: prepare a
#     celestial checkout, generate every colour's colors.def + SCSS, render
#     just the KDE artifacts (src/kde/render.sh), then stage that rendered KDE
#     tree into the celestial-themes package repo's kde/ dir.
#   - After this runs, rebuild the celestial-themes package with its build.sh.
#
#   Why: an upstream push that only adds KDE (celestial-gtk-theme 1.5.0) needs
#   only the kde/ folder created. render.sh compiles its own SCSS from the
#   colour palette, so this skips the slow ~1h Inkscape asset render entirely
#   (parse_sass.sh / render-all.sh) — the KDE render alone takes minutes.
#
#   Note: this touches ONLY the KDE tree. The GTK theme folders and Kvantum/
#   already sit committed in celestial-themes and this upstream change does not
#   affect them, so they are deliberately left as-is.
#####################################################################
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# Throwaway checkout by default (matches celestial-dir.sh); override to keep one.
CELESTIAL_DIR="${CELESTIAL_DIR:-/tmp/celestial-gtk-theme}"
# The celestial-themes package repo that receives the rendered KDE tree.
CT_DIR="${CT_DIR:-${HOME}/EDU/celestial-themes}"

#####################################################################
# Colors
#####################################################################
if command -v tput >/dev/null 2>&1 && [[ -t 1 ]]; then
    RED="$(tput setaf 1)"
    GREEN="$(tput setaf 2)"
    YELLOW="$(tput setaf 3)"
    BLUE="$(tput setaf 4)"
    CYAN="$(tput setaf 6)"
    RESET="$(tput sgr0)"
else
    RED="" GREEN="" YELLOW="" BLUE="" CYAN="" RESET=""
fi

#####################################################################
# Logging
#####################################################################
log_section() {
    echo
    echo "${GREEN}############################################################################${RESET}"
    echo "$1"
    echo "${GREEN}############################################################################${RESET}"
    echo
}

log_info() {
    echo
    echo "${BLUE}############################################################################${RESET}"
    echo "$1"
    echo "${BLUE}############################################################################${RESET}"
    echo
}

log_warn() {
    echo
    echo "${YELLOW}############################################################################${RESET}"
    echo "$1"
    echo "${YELLOW}############################################################################${RESET}"
    echo
}

log_error() {
    echo
    echo "${RED}############################################################################${RESET}"
    echo "$1"
    echo "${RED}############################################################################${RESET}"
    echo
}

log_success() {
    echo
    echo "${GREEN}############################################################################${RESET}"
    echo "$1"
    echo "${GREEN}############################################################################${RESET}"
    echo
}

#####################################################################
# Error handling
#####################################################################
on_error() {
    local lineno="$1"
    local cmd="$2"
    echo
    echo "${RED}ERROR on line ${lineno}: ${cmd}${RESET}"
    echo
    sleep 10
}

trap 'on_error "$LINENO" "$BASH_COMMAND"' ERR

#####################################################################
# Functions
#####################################################################
prepare_checkout() {
    log_section "Preparing celestial checkout at ${CELESTIAL_DIR}"
    python3 "${SCRIPT_DIR}/prepare-celestial.py" --dir "${CELESTIAL_DIR}"
}

generate_sources() {
    log_section "Generating every colour's colors.def + SCSS palette"
    CELESTIAL_DIR="${CELESTIAL_DIR}" bash "${SCRIPT_DIR}/generate-arc-colors.sh"
}

render_kde() {
    log_section "Rendering the KDE Plasma artifacts (all colours, one pass)"
    # render.sh compiles its own SCSS from src/gtk/sass, so it needs neither
    # parse_sass.sh nor the Inkscape asset render — only colors.def + the SCSS
    # palette that generate_sources just produced.
    CELESTIAL_DIR="${CELESTIAL_DIR}" bash "${CELESTIAL_DIR}/src/kde/render.sh"
}

stage_kde() {
    local kde_src="${CELESTIAL_DIR}/src/kde"
    log_section "Staging KDE tree into ${CT_DIR}/kde"

    [[ -d "${CT_DIR}" ]] || { log_error "celestial-themes repo not found at ${CT_DIR}"; exit 1; }
    for d in color-schemes look-and-feel desktoptheme aurorae; do
        [[ -d "${kde_src}/${d}" ]] || { log_error "missing rendered dir: ${kde_src}/${d}"; exit 1; }
    done

    install -dm755 "${CT_DIR}/kde"
    # Replace each family wholesale so removed/renamed variants never linger.
    for d in color-schemes look-and-feel desktoptheme aurorae; do
        rm -rf "${CT_DIR}/kde/${d}"
        cp -r "${kde_src}/${d}" "${CT_DIR}/kde/${d}"
        log_info "staged kde/${d} ($(find "${CT_DIR}/kde/${d}" -maxdepth 1 -mindepth 1 | wc -l) entries)"
    done
}

#####################################################################
# Main
#####################################################################
main() {
    prepare_checkout
    generate_sources
    render_kde
    stage_kde

    log_success "$(basename "$0") done — KDE tree staged in ${CT_DIR}/kde.
Next: rebuild the celestial-themes package with its build.sh."
}

main "$@"
