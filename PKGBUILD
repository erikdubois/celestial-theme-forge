# Maintainer: Erik Dubois <erik.dubois@gmail.com>

pkgname=celestial-theme-forge
pkgver=26.06
pkgrel=1
pkgdesc="Reproducible generator that expands the Celestial GTK theme with the 54-colour named Arc palette"
arch=('any')
url="https://github.com/erikdubois/celestial-theme-forge"
license=('GPL3')
depends=('bash' 'python' 'sassc' 'inkscape' 'imagemagick')
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
  install -Dm755 render-all.sh          "$sharedir/render-all.sh"
  install -Dm755 arc-colors-recolor.py  "$sharedir/arc-colors-recolor.py"
  install -Dm755 arc-colors-scss.py     "$sharedir/arc-colors-scss.py"
  install -Dm755 theme-forge-picker.py  "$sharedir/theme-forge-picker.py"

  # Wrappers on PATH
  install -d "$pkgdir/usr/bin"
  ln -s "/usr/share/$pkgname/generate-arc-colors.sh" "$pkgdir/usr/bin/celestial-theme-forge"
  ln -s "/usr/share/$pkgname/theme-forge-picker.py"  "$pkgdir/usr/bin/theme-forge-picker"

  # Docs
  install -Dm644 README.md    "$pkgdir/usr/share/doc/$pkgname/README.md"
  install -Dm644 CHANGELOG.md "$pkgdir/usr/share/doc/$pkgname/CHANGELOG.md"
}
