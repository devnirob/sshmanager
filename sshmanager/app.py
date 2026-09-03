from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk

from .config import APP_ID, APP_NAME
from .system_ssh import missing_dependencies


class SSHManagerApplication(Gtk.Application):
    def __init__(self) -> None:
        GLib.set_prgname(APP_ID)
        GLib.set_application_name(APP_NAME)
        Gtk.Window.set_default_icon_name(APP_ID)
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)

    def do_activate(self) -> None:
        missing = missing_dependencies()
        if missing:
            self._show_missing_dependencies(missing)
            return
        from .ui import MainWindow

        window = self.props.active_window
        if window is None:
            window = MainWindow(self)
        window.show_all()
        window.present()

    def _show_missing_dependencies(self, packages: list[str]) -> None:
        window = Gtk.ApplicationWindow(application=self, title=f"{APP_NAME} setup")
        window.set_icon_name(APP_ID)
        window.set_default_size(620, 300)
        window.set_border_width(28)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        window.add(box)
        title = Gtk.Label()
        title.set_markup("<span size='x-large' weight='bold'>A few system packages are required</span>")
        title.set_xalign(0)
        box.pack_start(title, False, False, 0)
        detail = Gtk.Label(
            label="Install these Debian packages, then reopen SSH Manager. The offline .deb already includes them."
        )
        detail.set_xalign(0)
        detail.set_line_wrap(True)
        box.pack_start(detail, False, False, 0)
        command = "sudo apt install " + " ".join(packages)
        command_label = Gtk.Label(label=command)
        command_label.set_selectable(True)
        command_label.set_xalign(0)
        box.pack_start(command_label, False, False, 12)
        close = Gtk.Button(label="Close")
        close.connect("clicked", lambda *_: window.close())
        box.pack_end(close, False, False, 0)
        window.show_all()
        window.present()


def main() -> None:
    if "--check" in sys.argv:
        missing = missing_dependencies()
        if missing:
            print("Missing packages: " + " ".join(missing))
            raise SystemExit(1)
        print("SSH Manager dependencies are ready.")
        return
    app = SSHManagerApplication()
    raise SystemExit(app.run(sys.argv))


if __name__ == "__main__":
    main()
