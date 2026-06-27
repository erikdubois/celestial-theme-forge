#!/usr/bin/env python3
"""Recolor celestial 'aliz' template assets onto a new accent.

The accent slots in an aliz asset are exactly the saturated colors that appear
in it but NOT in its clean blue 'azul' sibling: the red accent (#f0544c), the
metacity accent (#d5372f), and the green switch/toggle slots (#2eb398/#41ceb2)
that upstream left un-recolored in aliz. Everything aliz shares with azul is a
semantic or structural color (close button, destructive, error, success green,
greys, Arc-blue highlight) and is left untouched.

For each accent hex we preserve its lightness/saturation offset from whichever
source base it derives from (red #f0544c or green #2eb398) and reproject it onto
the target hue. The two bases therefore both collapse onto the same target
accent, unifying the buggy green switch with the real accent.

Usage:
  arc-colors-recolor.py <target_hex> <azul_path> <aliz_copy_path> [<azul_path> <aliz_copy_path> ...]

Each (azul_path, aliz_copy_path) pair may be two files or two directories. For
directories, files are paired by relative path and aliz_copy_path is recolored
in place.
"""
import colorsys
import os
import re
import sys

SOURCE_BASES = ["f0544c", "2eb398"]
SAT_THRESHOLD = 0.30
HEX_RE = re.compile(r"#([0-9a-fA-F]{6})")


def to_hls(h):
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return colorsys.rgb_to_hls(r, g, b)


def to_hex(hue, light, sat):
    r, g, b = colorsys.hls_to_rgb(hue % 1.0, max(0, min(1, light)), max(0, min(1, sat)))
    return "%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def hue_dist(h1, h2):
    d = abs(h1 - h2) % 1.0
    return min(d, 1.0 - d)


def file_hexes(path):
    try:
        text = open(path, encoding="utf-8", errors="ignore").read()
    except OSError:
        return set()
    return {m.lower() for m in HEX_RE.findall(text)}


def build_map(accent_hexes, target):
    """Map each aliz-only accent hex to the target, preserving its shade offset."""
    th, _tl, _ts = to_hls(target)
    bases = [(b, to_hls(b)) for b in SOURCE_BASES]
    cmap = {}
    for h in accent_hexes:
        sh, sl, ss = to_hls(h)
        _b, (bh, bl, bs) = min(bases, key=lambda x: hue_dist(x[1][0], sh))
        cmap[h] = to_hex(th, _tl - bl + sl, _ts - bs + ss)
    return cmap


def accent_hexes(azul_path, aliz_path):
    """Saturated hexes present in aliz but absent from its azul sibling."""
    azul = file_hexes(azul_path)
    out = set()
    for h in file_hexes(aliz_path):
        if h in azul:
            continue
        _hu, _li, sat = to_hls(h)
        if sat >= SAT_THRESHOLD:
            out.add(h)
    return out


def recolor(path, cmap):
    text = open(path, encoding="utf-8", errors="ignore").read()
    changed = 0

    def repl(m):
        nonlocal changed
        old = m.group(1).lower()
        if old in cmap:
            changed += 1
            return "#" + cmap[old]
        return m.group(0)

    new = HEX_RE.sub(repl, text)
    if changed:
        open(path, "w", encoding="utf-8").write(new)
    return changed


def iter_pairs(azul_path, aliz_path):
    if os.path.isdir(aliz_path):
        for root, _dirs, files in os.walk(aliz_path):
            for name in files:
                if not name.lower().endswith((".svg", ".xml")):
                    continue
                ap = os.path.join(root, name)
                rel = os.path.relpath(ap, aliz_path)
                yield os.path.join(azul_path, rel), ap
    else:
        yield azul_path, aliz_path


def main():
    if len(sys.argv) < 4 or len(sys.argv) % 2 != 0:
        sys.exit(__doc__)
    target = sys.argv[1].lstrip("#").lower()
    total = 0
    for i in range(2, len(sys.argv), 2):
        for azul_file, aliz_file in iter_pairs(sys.argv[i], sys.argv[i + 1]):
            cmap = build_map(accent_hexes(azul_file, aliz_file), target)
            if cmap:
                total += recolor(aliz_file, cmap)
    print(f"recolored {total} hex occurrences")


if __name__ == "__main__":
    main()
