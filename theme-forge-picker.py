#!/usr/bin/env python3
"""GTK4 picker that turns a chosen colour into an installed Celestial theme."""
import json
import os
import re
import subprocess
import sys
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
# Funding channels — keep in sync with the other Kiro tweak tools and
# kiro-website .github/FUNDING.yml if those change.
FUNDING = [
    ("GitHub Sponsors", "https://github.com/sponsors/erikdubois",
     "best value — almost all goes to the project"),
    ("Ko-fi", "https://ko-fi.com/erikdubois", "buy a coffee — one-off tip"),
    ("Patreon", "https://www.patreon.com/kiroproject", "membership tiers + perks"),
    ("YouTube membership", "https://www.youtube.com/@ErikDubois/join", "join on YouTube"),
    ("PayPal", "https://www.paypal.me/erikdubois", "direct one-off"),
]
# Screen eyedropper. X11 tools grab the root window; under Wayland that root
# belongs to XWayland and holds no composited output, so xcolor there returns a
# bogus colour (usually black) rather than failing — hence a per-session tool.
# -b drops the ANSI colouring hyprpicker otherwise wraps its output in.
# No -q for hyprpicker: it emits the picked colour through its own logger at a
# level --quiet suppresses, so quiet mode returns success with empty output.
EYEDROPPER_X11 = ["xcolor", "--format", "hex"]
EYEDROPPER_WAYLAND = ["hyprpicker", "-f", "hex", "-l", "-b"]
CSS = b"""
label#title { font-size: 20px; font-weight: 600; }
.support-button { color: #e0567a; }
.support-button:hover { background-color: alpha(#e0567a, 0.18); }
"""
# Kiro ships GTK_THEME="Arc-Dawn-Dark" in /etc/environment; while it is active it
# overrides every GTK theme, so a freshly built celestial theme appears to do nothing.
ENVIRONMENT_FILE = "/etc/environment"
GTK_THEME_RE = re.compile(r"^(\s*)(#+\s*)?(GTK_THEME=.*)$")
TERMINALS = ["alacritty", "kitty", "foot", "wezterm", "xfce4-terminal", "gnome-terminal", "xterm"]


def is_kiro():
    """True on a Kiro install (Arch-based, tagged via IMAGE_ID in os-release)."""
    try:
        text = open("/etc/os-release", encoding="utf-8").read()
    except OSError:
        return False
    return re.search(r"^IMAGE_ID=\"?kiro\"?$", text, re.MULTILINE) is not None


def gtk_theme_state():
    """'commented' | 'active' | None — state of the GTK_THEME line in /etc/environment."""
    try:
        for line in open(ENVIRONMENT_FILE, encoding="utf-8"):
            m = GTK_THEME_RE.match(line.rstrip("\n"))
            if m:
                return "commented" if m.group(2) else "active"
    except OSError:
        pass
    return None


# Cloned checkouts land in /tmp: throwaway, always writable, no assumptions
# about the user's home layout. Mirrors celestial-dir.sh.
CELESTIAL_DEFAULT_DIR = "/tmp/celestial-gtk-theme"


def celestial_dir_valid(path):
    return os.path.isdir(os.path.join(path, "src", "gtk")) and \
        os.path.isfile(os.path.join(path, "install.sh"))


def extract_hex(stdout):
    """Last hex line in a picker's output ('' if none) — hyprpicker also logs warnings."""
    for line in reversed(stdout.splitlines()):
        if HEX_RE.match(line.strip()):
            return line.strip()
    return ""


def eyedropper_argv():
    """Screen-picker argv for this session (Wayland: hyprpicker, X11: xcolor)."""
    return EYEDROPPER_WAYLAND if os.environ.get("WAYLAND_DISPLAY") else EYEDROPPER_X11


def resolve_celestial_dir():
    """$CELESTIAL_DIR, else this tree, else a sibling checkout, else the /tmp default."""
    env = os.environ.get("CELESTIAL_DIR")
    if env:
        return env
    for candidate in (SCRIPT_DIR,
                      os.path.join(os.path.dirname(SCRIPT_DIR), "celestial-gtk-theme")):
        if celestial_dir_valid(candidate):
            return candidate
    return CELESTIAL_DEFAULT_DIR


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

        # ── header ──────────────────────────────────────────────────────
        hrow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title = Gtk.Label(label="Celestial Theme Forge", xalign=0, hexpand=True)
        title.set_name("title")
        support_btn = Gtk.Button(label="♥ Support",
                                 tooltip_text="Support Kiro's development")
        support_btn.add_css_class("support-button")
        support_btn.connect("clicked", self._on_support)
        quit_btn = Gtk.Button(label="Quit")
        quit_btn.connect("clicked", lambda _w: self.close())
        for w in (title, support_btn, quit_btn):
            hrow.append(w)
        box.append(hrow)
        box.append(Gtk.Separator())

        # ── theme source ────────────────────────────────────────────────
        srow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.source_label = Gtk.Label(xalign=0, hexpand=True, wrap=True)
        self.source_label.add_css_class("dim-label")
        self.source_btn = Gtk.Button(label="Get theme source")
        self.source_btn.connect("clicked", self._on_get_source)
        srow.append(self.source_label)
        srow.append(self.source_btn)
        box.append(srow)

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
        tool = eyedropper_argv()[0]
        if not GLib.find_program_in_path(tool):
            pick_btn.set_sensitive(False)
            pick_btn.set_tooltip_text(f"Install {tool} for the screen eyedropper")
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

        # ── Kiro: /etc/environment GTK_THEME override ───────────────────
        self.env_hint = None
        if is_kiro() and gtk_theme_state():
            box.append(self._heading("4. Kiro: GTK_THEME override"))
            erow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            self.env_toggle_btn = Gtk.Button()
            self.env_toggle_btn.connect("clicked", self._on_env_toggle)
            edit_btn = Gtk.Button(label="Edit in nano")
            edit_btn.connect("clicked", self._on_env_edit)
            erow.append(self.env_toggle_btn)
            erow.append(edit_btn)
            box.append(erow)
            self.env_hint = Gtk.Label(xalign=0, wrap=True)
            self.env_hint.add_css_class("dim-label")
            box.append(self.env_hint)
            self._refresh_env_state()

        scroller = Gtk.ScrolledWindow(vexpand=True)
        self.log_view = Gtk.TextView(editable=False, monospace=True, cursor_visible=False)
        scroller.set_child(self.log_view)
        box.append(scroller)

        self._refresh_source_state()
        self._on_name_changed(self.name_entry)

    # ── support dialog ─────────────────────────────────────────────────
    def _on_support(self, _widget):
        dlg = Gtk.Window(title="Support Kiro", transient_for=self, modal=True)
        dlg.set_default_size(440, -1)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                      margin_top=18, margin_bottom=18, margin_start=18, margin_end=18)
        box.append(self._heading("Support Kiro"))
        intro = Gtk.Label(
            label="Kiro and its tools are built by one person, for the community — "
                  "and kept free. If Celestial Theme Forge saves you time, a little "
                  "support keeps the work going. Thank you for being here.",
            xalign=0, wrap=True, max_width_chars=52)
        intro.add_css_class("dim-label")
        box.append(intro)

        for name, url, note in FUNDING:
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            label = Gtk.Label(xalign=0)
            label.set_markup(f"<b>{name}</b>")
            hint = Gtk.Label(label=note, xalign=0)
            hint.add_css_class("dim-label")
            content.append(label)
            content.append(hint)
            btn = Gtk.Button(child=content)
            btn.connect("clicked", lambda _w, u=url: Gtk.UriLauncher.new(u).launch(dlg, None, None))
            box.append(btn)

        close = Gtk.Button(label="Close", halign=Gtk.Align.END)
        close.connect("clicked", lambda _w: dlg.close())
        box.append(close)
        dlg.set_child(box)
        dlg.present()

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
        # Append newest at the end; when an 11th arrives, the oldest (slot 1,
        # leftmost) drops off the front.
        hexv = ("#" + hexv.lstrip("#")).lower()
        self.recent = [c for c in self.recent if c != hexv] + [hexv]
        self.recent = self.recent[-RECENT_MAX:]
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
            rgba = dialog.get_rgba()
            self._set_hex_from_rgba(rgba)
            self._remember_color(self._current_hex() or rgba.to_string())
        dialog.destroy()

    def _set_hex_from_rgba(self, rgba):
        self.hex_entry.set_text("#%02x%02x%02x" % (
            round(rgba.red * 255), round(rgba.green * 255), round(rgba.blue * 255)))

    def _on_eyedropper(self, _widget):
        argv = eyedropper_argv()
        if not GLib.find_program_in_path(argv[0]):
            self.log(f"{argv[0]} not installed; use Choose… instead.\n")
            return
        threading.Thread(target=self._eyedropper_worker, args=(argv,), daemon=True).start()

    def _eyedropper_worker(self, argv):
        try:
            out = subprocess.run(argv, capture_output=True, text=True, timeout=60)
            hexv = extract_hex(out.stdout)
        except (OSError, subprocess.TimeoutExpired):
            hexv = ""
        if HEX_RE.match(hexv):
            GLib.idle_add(self.hex_entry.set_text, hexv.lower())
            GLib.idle_add(self._remember_color, hexv.lower())

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

    # ── theme source ─────────────────────────────────────────────────────
    def _refresh_source_state(self):
        ready = celestial_dir_valid(CELESTIAL_DIR)
        self.source_btn.set_label("Re-clone theme source" if ready else "Clone theme source")
        self.source_btn.set_tooltip_text(
            f"Delete {CELESTIAL_DIR} and clone it again" if ready
            else f"Clone the celestial theme into {CELESTIAL_DIR}")
        if ready:
            self.source_label.set_text(f"Theme source: {CELESTIAL_DIR}")
        else:
            self.source_label.set_text(
                f"No theme source at {CELESTIAL_DIR} — clone and prepare it first.")
        self._refresh_create_sensitivity()

    def _on_get_source(self, _widget):
        if self._busy:
            return
        if not celestial_dir_valid(CELESTIAL_DIR):
            self._start_source_fetch(force=False)
            return
        # Re-clone throws away the whole checkout — every rendered asset and any
        # local edit — so name the path and make the user say so.
        dialog = Gtk.AlertDialog(
            message="Re-clone the theme source?",
            detail=f"{CELESTIAL_DIR} will be deleted and cloned again.\n"
                   "All rendered assets and any local changes there are lost.",
            buttons=["Cancel", "Re-clone"], cancel_button=0, default_button=0)
        dialog.choose(self, None, self._on_reclone_answer)

    def _on_reclone_answer(self, dialog, result):
        try:
            confirmed = dialog.choose_finish(result) == 1
        except GLib.Error:  # dismissed with Escape
            confirmed = False
        if confirmed:
            self._start_source_fetch(force=True)

    def _start_source_fetch(self, force):
        self._busy = True
        self.source_btn.set_sensitive(False)
        self._refresh_create_sensitivity()
        verb = "Re-cloning" if force else "Fetching"
        self.log(f"\n=== {verb} celestial theme source into {CELESTIAL_DIR} ===\n")
        threading.Thread(target=self._source_worker, args=(force,), daemon=True).start()

    def _source_worker(self, force):
        argv = [sys.executable, os.path.join(SCRIPT_DIR, "prepare-celestial.py"),
                "--dir", CELESTIAL_DIR]
        if force:
            argv.append("--force")
        try:
            proc = subprocess.Popen(argv, cwd=SCRIPT_DIR, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True)
        except OSError as exc:
            GLib.idle_add(self.log, f"failed to start prepare-celestial.py: {exc}\n")
            GLib.idle_add(self._source_done, 1)
            return
        for line in proc.stdout:
            GLib.idle_add(self.log, line)
        GLib.idle_add(self._source_done, proc.wait())

    def _source_done(self, rc):
        self._busy = False
        self.source_btn.set_sensitive(True)
        if rc != 0:
            self.log(f"\n*** Could not prepare the theme source (exit {rc}) ***\n")
        self._refresh_source_state()

    # ── create / build pipeline ──────────────────────────────────────────
    def _refresh_create_sensitivity(self):
        name = sanitize_name(self.name_entry.get_text())
        ok = (bool(self._current_hex()) and self._name_status(name) in ("new", "rebuild")
              and celestial_dir_valid(CELESTIAL_DIR))
        self.create_btn.set_sensitive(ok and not self._busy)

    def _on_create(self, _widget):
        hexv = self._current_hex()
        name = sanitize_name(self.name_entry.get_text())
        if not (hexv and name) or self._busy:
            return
        self._busy = True
        self.create_btn.set_sensitive(False)
        self.create_spinner.start()
        self.log(f"\n=== Building '{name}' ({hexv}) — this takes a few minutes ===\n")
        threading.Thread(target=self._build_worker, args=(name, hexv), daemon=True).start()

    def _build_worker(self, name, hexv):
        base_env = dict(os.environ, CELESTIAL_DIR=CELESTIAL_DIR)
        # Each step scoped to the single colour: render takes <name>, parse_sass
        # honours THEME_VARIANTS, install takes -t <name> (-k adds the Qt/Kvantum theme).
        steps = [
            ("generate", [os.path.join(SCRIPT_DIR, "generate-arc-colors.sh"),
                          "--add", name, hexv.lstrip("#")], SCRIPT_DIR, {}),
            ("parse_sass", [os.path.join(CELESTIAL_DIR, "parse_sass.sh")],
             CELESTIAL_DIR, {"THEME_VARIANTS": f"-{name}"}),
            ("render", [os.path.join(SCRIPT_DIR, "render-all.sh"), name], SCRIPT_DIR, {}),
            ("install", [os.path.join(CELESTIAL_DIR, "install.sh"), "-t", name, "-k"],
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

    # ── Kiro /etc/environment callbacks ──────────────────────────────────
    def _refresh_env_state(self):
        state = gtk_theme_state()
        if state == "commented":
            self.env_toggle_btn.set_label("Re-enable GTK_THEME (add back)")
            self.env_hint.set_text(
                "GTK_THEME is commented out — celestial themes apply normally.")
        elif state == "active":
            self.env_toggle_btn.set_label("Comment out GTK_THEME (#)")
            self.env_hint.set_text(
                "GTK_THEME is active and overrides every GTK theme — comment it out "
                "to let celestial themes apply.")
        else:
            self.env_toggle_btn.set_sensitive(False)
            self.env_hint.set_text("No GTK_THEME line found in /etc/environment.")

    def _on_env_toggle(self, _widget):
        state = gtk_theme_state()
        if not state:
            self._refresh_env_state()
            return
        if state == "active":
            expr = r"s/^\(\s*\)\(GTK_THEME=\)/\1#\2/"
        else:
            expr = r"s/^\(\s*\)#\+\s*\(GTK_THEME=\)/\1\2/"
        self.env_toggle_btn.set_sensitive(False)
        threading.Thread(target=self._env_toggle_worker, args=(expr,), daemon=True).start()

    def _env_toggle_worker(self, expr):
        proc = subprocess.Popen(["pkexec", "/usr/bin/sed", "-i", expr, ENVIRONMENT_FILE],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        out = proc.stdout.read()
        rc = proc.wait()
        GLib.idle_add(self._env_toggle_done, rc, out)

    def _env_toggle_done(self, rc, out):
        self.env_toggle_btn.set_sensitive(True)
        if rc != 0:
            self.log(f"\nEditing {ENVIRONMENT_FILE} failed (exit {rc}). {out}\n")
        else:
            self.log(f"\n{ENVIRONMENT_FILE} updated — log out and back in for it to take effect.\n")
        self._refresh_env_state()

    def _on_env_edit(self, _widget):
        term = os.environ.get("TERMINAL") or next(
            (t for t in TERMINALS if GLib.find_program_in_path(t)), None)
        if not term:
            self.log("\nNo terminal emulator found; run 'sudo nano /etc/environment' yourself.\n")
            return
        proc = subprocess.Popen([term, "-e", "sudo", "nano", ENVIRONMENT_FILE])
        self.log(f"\nOpened {ENVIRONMENT_FILE} in nano ({term}).\n")
        threading.Thread(target=self._env_edit_watcher, args=(proc,), daemon=True).start()

    def _env_edit_watcher(self, proc):
        proc.wait()
        GLib.idle_add(self._refresh_env_state)

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
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        PickerWindow(self).present()


if __name__ == "__main__":
    PickerApp().run(None)
