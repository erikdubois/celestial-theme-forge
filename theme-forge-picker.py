#!/usr/bin/env python3
"""GTK4 picker that turns a chosen colour into an installed Celestial theme."""
import json
import os
import re
import subprocess
import threading
import urllib.error
import urllib.request

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# custom-colors.def lives in-tree for a writable dev checkout, else in a per-user
# XDG path (matches generate-arc-colors.sh, which actually writes it).
if os.access(SCRIPT_DIR, os.W_OK):
    CUSTOM_DEF = os.path.join(SCRIPT_DIR, "custom-colors.def")
else:
    CUSTOM_DEF = os.path.join(
        os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
        "celestial-theme-forge", "custom-colors.def")
HEX_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")
USER_AGENT = "celestial-theme-forge/1.0"  # api.color.pizza 403s the default urllib UA
# color-names lists to sample for varied suggestions (api.color.pizza).
NAME_LISTS = ["", "bestOf", "wikipedia", "x11", "ntc"]
# Recently-built colours, newest first — pure user state, always in XDG config.
RECENT_FILE = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
    "celestial-theme-forge", "recent-colors")
RECENT_MAX = 10


def resolve_celestial_dir():
    env = os.environ.get("CELESTIAL_DIR")
    if env:
        return env
    if os.path.isdir(os.path.join(SCRIPT_DIR, "src", "gtk")):
        return SCRIPT_DIR
    return "/home/erik/DATA/celestial-gtk-theme"


CELESTIAL_DIR = resolve_celestial_dir()


def sanitize_name(raw):
    """Lowercase, spaces->hyphens, keep only [a-z0-9-] (mirrors the generator)."""
    name = raw.strip().lower().replace(" ", "-")
    name = re.sub(r"[^a-z0-9-]", "", name)
    return re.sub(r"-+", "-", name).strip("-")


def existing_names():
    """Names already defined in the target checkout's colors.def (THEME_COLORS)."""
    path = os.path.join(CELESTIAL_DIR, "src", "colors.def")
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return set()
    m = re.search(r"THEME_COLORS=\(([^)]*)\)", text)
    return set(m.group(1).split()) if m else set()


def custom_names():
    """Names recorded in custom-colors.def — rebuildable, so not blocked."""
    names = set()
    try:
        for line in open(CUSTOM_DEF, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#"):
                names.add(line.split()[0])
    except OSError:
        pass
    return names


def load_recent():
    """Recently-built colours as '#rrggbb' strings, newest first (max RECENT_MAX)."""
    out = []
    try:
        for line in open(RECENT_FILE, encoding="utf-8"):
            h = line.strip().lower()
            if HEX_RE.match(h) and h not in out:
                out.append("#" + h.lstrip("#"))
    except OSError:
        pass
    return out[:RECENT_MAX]


def save_recent(colors):
    os.makedirs(os.path.dirname(RECENT_FILE), exist_ok=True)
    with open(RECENT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(colors[:RECENT_MAX]) + "\n")


def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=6) as resp:
        return json.load(resp)


def fetch_name_suggestions(hexv):
    """Query online colour-name databases; return de-duplicated raw name list."""
    h = hexv.lstrip("#").lower()
    seen, names = set(), []

    def add(raw):
        if not raw:
            return
        key = sanitize_name(raw)
        if key and key not in seen:
            seen.add(key)
            names.append(raw)

    for lst in NAME_LISTS:
        url = f"https://api.color.pizza/v1/?values={h}"
        if lst:
            url += f"&list={lst}"
        try:
            cols = _get_json(url).get("colors") or []
            if cols:
                add(cols[0].get("name"))
        except (urllib.error.URLError, ValueError, OSError):
            continue
    try:
        add((_get_json(f"https://www.thecolorapi.com/id?hex={h}").get("name") or {}).get("value"))
    except (urllib.error.URLError, ValueError, OSError):
        pass
    return names[:6]


class PickerWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Celestial Theme Forge")
        self.set_default_size(560, 640)
        self.rgba = Gdk.RGBA()
        self.rgba.parse("#8d2dc9")
        self._busy = False
        self.recent = load_recent()

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                      margin_top=14, margin_bottom=14, margin_start=14, margin_end=14)
        self.set_child(box)

        # ── colour input ────────────────────────────────────────────────
        box.append(self._heading("1. Pick a colour"))
        crow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.hex_entry = Gtk.Entry(text="#8d2dc9", max_length=7, hexpand=True,
                                   placeholder_text="#rrggbb")
        self.hex_entry.connect("changed", self._on_hex_changed)
        self.swatch = Gtk.DrawingArea(content_width=44, content_height=34)
        self.swatch.set_draw_func(self._draw_swatch)
        choose_btn = Gtk.Button(label="Choose…")
        choose_btn.connect("clicked", self._on_choose)
        pick_btn = Gtk.Button(label="Pick from screen")
        pick_btn.connect("clicked", self._on_eyedropper)
        for w in (self.hex_entry, self.swatch, choose_btn, pick_btn):
            crow.append(w)
        box.append(crow)

        # ── recent colours ──────────────────────────────────────────────
        self.recent_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        rlabel = Gtk.Label(label="Recent:", xalign=0)
        rlabel.add_css_class("dim-label")
        self.recent_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.recent_row.append(rlabel)
        self.recent_row.append(self.recent_box)
        box.append(self.recent_row)
        self._refresh_recent()

        # ── name research ───────────────────────────────────────────────
        box.append(self._heading("2. Name it"))
        nrow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.lookup_btn = Gtk.Button(label="Look up names online")
        self.lookup_btn.connect("clicked", self._on_lookup)
        self.lookup_spinner = Gtk.Spinner()
        nrow.append(self.lookup_btn)
        nrow.append(self.lookup_spinner)
        box.append(nrow)

        self.suggestions = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,
                                       max_children_per_line=3, row_spacing=4,
                                       column_spacing=4)
        box.append(self.suggestions)

        self.name_entry = Gtk.Entry(placeholder_text="theme colour name (lowercase-hyphen)")
        self.name_entry.connect("changed", self._on_name_changed)
        box.append(self.name_entry)
        self.name_hint = Gtk.Label(xalign=0)
        self.name_hint.add_css_class("dim-label")
        box.append(self.name_hint)

        # ── create ──────────────────────────────────────────────────────
        box.append(self._heading("3. Build &amp; install"))
        brow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.create_btn = Gtk.Button(label="Create theme → ~/.themes")
        self.create_btn.add_css_class("suggested-action")
        self.create_btn.connect("clicked", self._on_create)
        self.create_spinner = Gtk.Spinner()
        brow.append(self.create_btn)
        brow.append(self.create_spinner)
        box.append(brow)

        scroller = Gtk.ScrolledWindow(vexpand=True)
        self.log_view = Gtk.TextView(editable=False, monospace=True, cursor_visible=False)
        scroller.set_child(self.log_view)
        box.append(scroller)

        self._on_name_changed(self.name_entry)

    # ── small helpers ──────────────────────────────────────────────────
    def _heading(self, text):
        lbl = Gtk.Label(xalign=0)
        lbl.set_markup(f"<b>{text}</b>")
        return lbl

    def _draw_swatch(self, _area, ctx, width, height):
        ctx.set_source_rgb(self.rgba.red, self.rgba.green, self.rgba.blue)
        ctx.rectangle(0, 0, width, height)
        ctx.fill()

    # ── recent colours ──────────────────────────────────────────────────
    def _refresh_recent(self):
        child = self.recent_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.recent_box.remove(child)
            child = nxt
        # Always show RECENT_MAX slots: filled ones first, empty placeholders after.
        for i in range(RECENT_MAX):
            if i < len(self.recent):
                self.recent_box.append(self._recent_swatch(self.recent[i]))
            else:
                self.recent_box.append(self._empty_swatch())

    def _recent_swatch(self, hexv):
        rgba = Gdk.RGBA()
        rgba.parse(hexv)
        area = Gtk.DrawingArea(content_width=22, content_height=18)
        area.set_draw_func(
            lambda _a, ctx, w, h, c=rgba: (ctx.set_source_rgb(c.red, c.green, c.blue),
                                           ctx.rectangle(0, 0, w, h), ctx.fill()))
        btn = Gtk.Button(child=area, tooltip_text=hexv)
        btn.add_css_class("flat")
        btn.connect("clicked", lambda _b, h=hexv: self.hex_entry.set_text(h))
        return btn

    def _empty_swatch(self):
        area = Gtk.DrawingArea(content_width=22, content_height=18)
        area.set_draw_func(self._draw_empty_slot)
        btn = Gtk.Button(child=area, sensitive=False)
        btn.add_css_class("flat")
        return btn

    @staticmethod
    def _draw_empty_slot(_a, ctx, w, h):
        ctx.set_source_rgba(0.5, 0.5, 0.5, 0.4)
        ctx.set_line_width(1)
        ctx.rectangle(0.5, 0.5, w - 1, h - 1)
        ctx.stroke()

    def _remember_color(self, hexv):
        hexv = ("#" + hexv.lstrip("#")).lower()
        self.recent = [hexv] + [c for c in self.recent if c != hexv]
        self.recent = self.recent[:RECENT_MAX]
        save_recent(self.recent)
        self._refresh_recent()

    def _current_hex(self):
        t = self.hex_entry.get_text().strip()
        return ("#" + t.lstrip("#")).lower() if HEX_RE.match(t) else None

    def log(self, text):
        buf = self.log_view.get_buffer()
        buf.insert(buf.get_end_iter(), text)
        mark = buf.create_mark(None, buf.get_end_iter(), False)
        self.log_view.scroll_mark_onscreen(mark)

    # ── colour input callbacks ─────────────────────────────────────────
    def _on_hex_changed(self, _entry):
        hexv = self._current_hex()
        if hexv:
            self.rgba.parse(hexv)
            self.swatch.queue_draw()
        self._refresh_create_sensitivity()

    def _on_choose(self, _widget):
        # Open the chooser pre-seeded with the current colour. Build the RGBA
        # fresh from the entry so it can't lag behind a just-typed value.
        initial = Gdk.RGBA()
        if not initial.parse(self._current_hex() or self.rgba.to_string()):
            initial = self.rgba
        # Gtk.ColorChooserDialog (deprecated but reliable) opens its editor
        # directly on the set colour; Gtk.ColorDialog only selects it in the
        # palette grid, leaving the editor screen on its default red.
        dialog = Gtk.ColorChooserDialog(title="Pick a colour", transient_for=self,
                                        modal=True, show_editor=True)
        dialog.set_rgba(initial)
        dialog.connect("response", self._on_chosen)
        dialog.present()

    def _on_chosen(self, dialog, response):
        if response == Gtk.ResponseType.OK:
            self._set_hex_from_rgba(dialog.get_rgba())
        dialog.destroy()

    def _set_hex_from_rgba(self, rgba):
        self.hex_entry.set_text("#%02x%02x%02x" % (
            round(rgba.red * 255), round(rgba.green * 255), round(rgba.blue * 255)))

    def _on_eyedropper(self, _widget):
        if not GLib.find_program_in_path("xcolor"):
            self.log("xcolor not installed; use Choose… instead.\n")
            return
        threading.Thread(target=self._eyedropper_worker, daemon=True).start()

    def _eyedropper_worker(self):
        try:
            out = subprocess.run(["xcolor", "--format", "hex"],
                                 capture_output=True, text=True, timeout=60)
            hexv = out.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            hexv = ""
        if HEX_RE.match(hexv):
            GLib.idle_add(self.hex_entry.set_text, hexv.lower())

    # ── name research callbacks ─────────────────────────────────────────
    def _on_lookup(self, _widget):
        hexv = self._current_hex()
        if not hexv:
            self.log("Enter a valid #rrggbb hex first.\n")
            return
        self.lookup_btn.set_sensitive(False)
        self.lookup_spinner.start()
        threading.Thread(target=self._lookup_worker, args=(hexv,), daemon=True).start()

    def _lookup_worker(self, hexv):
        names = fetch_name_suggestions(hexv)
        GLib.idle_add(self._show_suggestions, names)

    def _show_suggestions(self, names):
        self.lookup_spinner.stop()
        self.lookup_btn.set_sensitive(True)
        child = self.suggestions.get_first_child()
        while child:
            self.suggestions.remove(child)
            child = self.suggestions.get_first_child()
        if not names:
            self.log("No name suggestions (offline?). Type one manually.\n")
            return
        for raw in names:
            btn = Gtk.Button(label=f"{raw}  ({sanitize_name(raw)})")
            btn.connect("clicked", self._on_pick_suggestion, raw)
            self.suggestions.append(btn)

    def _on_pick_suggestion(self, _widget, raw):
        self.name_entry.set_text(sanitize_name(raw))

    def _name_status(self, name):
        """'empty' | 'blocked' (built-in) | 'rebuild' (existing custom) | 'new'."""
        if not name:
            return "empty"
        if name in existing_names() - custom_names():
            return "blocked"
        if name in custom_names():
            return "rebuild"
        return "new"

    def _on_name_changed(self, _entry):
        name = sanitize_name(self.name_entry.get_text())
        hints = {
            "empty": "Name becomes a lowercase-hyphen slug.",
            "blocked": f"'{name}' is a built-in colour — choose another.",
            "rebuild": f"Will rebuild existing custom colour: {name}",
            "new": f"Will build as: {name}",
        }
        self.name_hint.set_text(hints[self._name_status(name)])
        self._refresh_create_sensitivity()

    # ── create / build pipeline ──────────────────────────────────────────
    def _refresh_create_sensitivity(self):
        name = sanitize_name(self.name_entry.get_text())
        ok = bool(self._current_hex()) and self._name_status(name) in ("new", "rebuild")
        self.create_btn.set_sensitive(ok and not self._busy)

    def _on_create(self, _widget):
        hexv = self._current_hex()
        name = sanitize_name(self.name_entry.get_text())
        if not (hexv and name) or self._busy:
            return
        self._remember_color(hexv)
        self._busy = True
        self.create_btn.set_sensitive(False)
        self.create_spinner.start()
        self.log(f"\n=== Building '{name}' ({hexv}) — this takes a few minutes ===\n")
        threading.Thread(target=self._build_worker, args=(name, hexv), daemon=True).start()

    def _build_worker(self, name, hexv):
        base_env = dict(os.environ, CELESTIAL_DIR=CELESTIAL_DIR)
        # Each step scoped to the single colour: render takes <name>, parse_sass
        # honours THEME_VARIANTS, install takes -t <name>.
        steps = [
            ("generate", [os.path.join(SCRIPT_DIR, "generate-arc-colors.sh"),
                          "--add", name, hexv.lstrip("#")], SCRIPT_DIR, {}),
            ("parse_sass", [os.path.join(CELESTIAL_DIR, "parse_sass.sh")],
             CELESTIAL_DIR, {"THEME_VARIANTS": f"-{name}"}),
            ("render", [os.path.join(SCRIPT_DIR, "render-all.sh"), name], SCRIPT_DIR, {}),
            ("install", [os.path.join(CELESTIAL_DIR, "install.sh"), "-t", name],
             CELESTIAL_DIR, {}),
        ]
        ok = True
        for label, argv, cwd, extra in steps:
            GLib.idle_add(self.log, f"\n--- {label}: {' '.join(argv)} ---\n")
            try:
                proc = subprocess.Popen(argv, cwd=cwd, env=dict(base_env, **extra),
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True)
            except OSError as exc:
                GLib.idle_add(self.log, f"failed to start {label}: {exc}\n")
                ok = False
                break
            for line in proc.stdout:
                GLib.idle_add(self.log, line)
            if proc.wait() != 0:
                GLib.idle_add(self.log, f"\n*** {label} failed (exit {proc.returncode}) ***\n")
                ok = False
                break
        GLib.idle_add(self._build_done, name, ok)

    def _build_done(self, name, ok):
        self._busy = False
        self.create_spinner.stop()
        self._refresh_create_sensitivity()
        if ok:
            self.log(f"\n=== Done. '{name}' installed under ~/.themes ===\n")
        else:
            self.log("\n=== Build stopped. See errors above. ===\n")


class PickerApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="be.kiroproject.CelestialThemeForge")

    def do_activate(self):
        PickerWindow(self).present()


if __name__ == "__main__":
    PickerApp().run(None)
