#!/bin/bash
set -euo pipefail
#####################################################################
# Author    : Erik Dubois
# Website   : https://kiroproject.be
#####################################################################
#
#   DO NOT JUST RUN THIS. EXAMINE AND JUDGE. RUN AT YOUR OWN RISK.
#
#   Purpose:
#   - One-shot shipper for the self-contained celestial-theme-forge
#     package repo (source + PKGBUILD live in the same folder).
#   - 1) wipe makepkg leftovers so the folder + the next git push stay clean
#   - 2) bump the PKGBUILD version (date-based pkgver, pkgrel auto-increments)
#   - 3) push the source to GitHub via up.sh  ── REQUIRED before building:
#        the PKGBUILD uses source=git+<github>, so makepkg pulls the payload
#        from GitHub, not from this local tree. No push = stale package.
#   - 4) build the package in /tmp (NEVER in this folder → folder stays clean)
#   - 5) copy the .pkg.tar.zst into nemesis_repo and publish it online
#        by running nemesis_repo/up.sh (repo-add + git commit + push)
#
#   Why: turn a finished local change into a live nemesis_repo package with
#   a single command, without ever cluttering this working directory.
#
#   NOTE: unlike the canonical flow-* split (source repo up.sh, then a
#   separate PKG-BUILD dir build.sh), this build.sh also does the source
#   push (step 3) because the source and the PKGBUILD share one folder.
#####################################################################

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

REPO_DIR="${HOME}/EDU/nemesis_repo"
DESTINY="${REPO_DIR}/x86_64"
CHROOT="${HOME}/Documents/chroot-archlinux"
TMPBUILD="/tmp/celestial-theme-forge-build"

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
clean_leftovers() {
    log_section "Cleaning makepkg leftovers"
    # makepkg dumps these into the source folder when run in place — wipe them
    # before up.sh runs `git add --all`, or they get committed and pushed.
    rm -rf "${SCRIPT_DIR}/src" \
           "${SCRIPT_DIR}/pkg" \
           "${SCRIPT_DIR}/celestial-theme-forge"
    find "${SCRIPT_DIR}" -maxdepth 1 -name '*.pkg.tar.zst' -delete
    find "${SCRIPT_DIR}" -maxdepth 1 -name '*.log' -delete
    find "${SCRIPT_DIR}" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
    log_success "Folder is clean"
}

bump_version() {
    local pkgbuild="${SCRIPT_DIR}/PKGBUILD"
    [[ ! -f "${pkgbuild}" ]] && { log_error "No PKGBUILD found in ${SCRIPT_DIR}"; exit 1; }

    local old_pkgver old_pkgrel new_pkgver new_pkgrel
    old_pkgver=$(grep -E '^pkgver=' "${pkgbuild}" | cut -d= -f2)
    old_pkgrel=$(grep -E '^pkgrel=' "${pkgbuild}" | cut -d= -f2)

    new_pkgver=$(date +%y.%m)
    if [[ "${new_pkgver}" != "${old_pkgver}" ]]; then
        new_pkgrel="01"
    else
        new_pkgrel=$(printf '%02d' $((10#${old_pkgrel} + 1)))
    fi

    sed -i "s/^pkgver=.*/pkgver=${new_pkgver}/" "${pkgbuild}"
    sed -i "s/^pkgrel=.*/pkgrel=${new_pkgrel}/" "${pkgbuild}"

    log_info "Version bump:
  pkgver: ${old_pkgver} → ${new_pkgver}
  pkgrel: ${old_pkgrel} → ${new_pkgrel}"
}

push_source() {
    # Push the source (incl. the bumped PKGBUILD) to GitHub FIRST, so the
    # git+url build clones the latest payload. up.sh = commit + push.
    log_section "Pushing source to GitHub (up.sh)"
    bash "${SCRIPT_DIR}/up.sh"
}

build_package() {
    log_section "Building celestial-theme-forge in CHROOT ${CHROOT}"

    rm -rf "${TMPBUILD}"
    mkdir -p "${TMPBUILD}"
    cp -r "${SCRIPT_DIR}/PKGBUILD" "${TMPBUILD}/"

    arch-nspawn "${CHROOT}/root" pacman -Syu --noconfirm

    if (cd "${TMPBUILD}" && makechrootpkg -c -r "${CHROOT}"); then
        log_section "Copying package to ${DESTINY}"
        install -d "${DESTINY}"
        cp -v "${TMPBUILD}"/*.pkg.tar.zst "${DESTINY}/"
    else
        log_error "Build failed — nothing copied to ${DESTINY}"
        rm -rf "${TMPBUILD}"
        exit 1
    fi

    rm -rf "${TMPBUILD}"
    log_success "Package built and staged in nemesis_repo"
}

publish_repo() {
    # nemesis_repo/up.sh runs repo.sh (repo-add) + git commit + push → live online.
    log_section "Publishing nemesis_repo online (up.sh)"
    bash "${REPO_DIR}/up.sh"
}

#####################################################################
# Main
#####################################################################
main() {
    clean_leftovers
    bump_version
    push_source
    build_package
    publish_repo

    log_success "$(basename "$0") done — celestial-theme-forge is live in nemesis_repo"
}

main "$@"
