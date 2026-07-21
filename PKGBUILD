# Maintainer: Erik Dubois <erik.dubois@gmail.com>

pkgname=celestial-theme-forge
pkgver=26.07
pkgrel=01
pkgdesc="Reproducible generator that expands the Celestial GTK theme with the 54-colour named Arc palette"
arch=('any')
url="https://github.com/erikdubois/celestial-theme-forge"
license=('GPL3')
depends=('bash' 'git' 'python' 'sassc' 'inkscape' 'imagemagick')
optdepends=('python-gobject: theme-forge-picker.py GTK4 GUI'
            'gtk4: theme-forge-picker.py GTK4 GUI'
            'xcolor: screen eyedropper for theme-forge-picker.py'
            'optipng: shrink rendered PNG assets')
makedepends=('git')
source=("${pkgname}::git+${url}.git")
sha256sums=('SKIP')

package() {
  cd "$srcdir/$pkgname"

  local sharedir="$pkgdir/usr/share/$pkgname"
  install -d "$sharedir"

  # Generator + render + recolour tooling
  install -Dm755 generate-arc-colors.sh "$sharedir/generate-arc-colors.sh"
  install -Dm644 celestial-dir.sh       "$sharedir/celestial-dir.sh"
  install -Dm755 prepare-celestial.py   "$sharedir/prepare-celestial.py"
  install -Dm755 render-all.sh          "$sharedir/render-all.sh"
  install -Dm755 arc-colors-recolor.py  "$sharedir/arc-colors-recolor.py"
  install -Dm755 arc-colors-scss.py     "$sharedir/arc-colors-scss.py"
  install -Dm755 theme-forge-picker.py  "$sharedir/theme-forge-picker.py"

  # Wrappers on PATH — exec the real scripts so they resolve their own
  # location (BASH_SOURCE / __file__) to the share dir, not /usr/bin.
  install -d "$pkgdir/usr/bin"
  printf '#!/bin/bash\nexec /usr/share/%s/generate-arc-colors.sh "$@"\n' \
    "$pkgname" > "$pkgdir/usr/bin/celestial-theme-forge"
  printf '#!/bin/bash\nexec python3 /usr/share/%s/theme-forge-picker.py "$@"\n' \
    "$pkgname" > "$pkgdir/usr/bin/theme-forge-picker"
  chmod 755 "$pkgdir/usr/bin/celestial-theme-forge" "$pkgdir/usr/bin/theme-forge-picker"

  # Desktop entry (app-menu launcher for the GUI)
  install -Dm644 theme-forge-picker.desktop \
    "$pkgdir/usr/share/applications/theme-forge-picker.desktop"

  # Docs
  install -Dm644 README.md    "$pkgdir/usr/share/doc/$pkgname/README.md"
  install -Dm644 CHANGELOG.md "$pkgdir/usr/share/doc/$pkgname/CHANGELOG.md"
}
