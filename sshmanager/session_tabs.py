from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GObject, Gtk

from .models import ConnectionProfile
from .sftp_browser import SFTPBrowserWidget
from .ssh_console import SSHConsoleWidget


class SessionTabs(Gtk.Box):
    """A notebook of independent SSH or SFTP connections."""

    __gsignals__ = {"status-changed": (GObject.SignalFlags.RUN_FIRST, None, (str,))}

    def __init__(self, kind: str, factory: Callable[[], Gtk.Widget], connect_method: str) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.kind = kind
        self.factory = factory
        self.connect_method = connect_method
        self.profile: ConnectionProfile | None = None
        self.password = ""
        self.theme = "vscode-dark"
        self.sessions: list[Gtk.Widget] = []

        toolbar = Gtk.Box(spacing=8)
        toolbar.get_style_context().add_class("session-strip")
        self.pack_start(toolbar, False, False, 0)
        new_button = Gtk.Button(label=f"+ New {kind} Tab")
        new_button.get_style_context().add_class("suggested-action")
        new_button.connect("clicked", lambda *_: self.open_session(connect=True))
        toolbar.pack_start(new_button, False, False, 0)
        hint = Gtk.Label(label="Each tab keeps its own server connection")
        hint.set_xalign(0)
        hint.get_style_context().add_class("muted-light")
        toolbar.pack_start(hint, False, False, 4)

        self.notebook = Gtk.Notebook()
        self.notebook.set_scrollable(True)
        self.notebook.set_show_border(False)
        self.pack_start(self.notebook, True, True, 0)

        self.empty = Gtk.Label(label=f"Select a saved server, then open a new {kind} tab.")
        self.empty.get_style_context().add_class("empty-state")
        self.pack_start(self.empty, True, True, 0)
        self.notebook.hide()

    def set_profile(self, profile: ConnectionProfile | None, password: str) -> None:
        self.profile = profile
        self.password = password

    def set_theme(self, theme: str) -> None:
        self.theme = theme
        if self.kind == "SSH":
            for session in self.sessions:
                session.set_theme(theme)

    def open_session(self, connect: bool = True) -> Gtk.Widget | None:
        if self.profile is None:
            self.emit("status-changed", "Select a server first.")
            return None
        errors = self.profile.validate()
        if errors:
            self.emit("status-changed", errors[0])
            return None

        # A session gets a snapshot so later profile edits cannot retarget it.
        profile = ConnectionProfile.from_dict(self.profile.to_dict())
        session = self.factory()
        session.set_profile(profile, self.password)
        if self.kind == "SSH":
            session.set_theme(self.theme)
        session.connect("status-changed", lambda _widget, message: self.emit("status-changed", message))
        self.sessions.append(session)

        tab = Gtk.Box(spacing=5)
        label = Gtk.Label(label=profile.name or profile.target)
        tab.pack_start(label, False, False, 0)
        close = Gtk.Button.new_from_icon_name("window-close-symbolic", Gtk.IconSize.MENU)
        close.set_relief(Gtk.ReliefStyle.NONE)
        close.set_tooltip_text(f"Close {self.kind} tab")
        close.connect("clicked", lambda *_: self.close_session(session))
        tab.pack_start(close, False, False, 0)
        tab.show_all()

        page = self.notebook.append_page(session, tab)
        self.notebook.set_tab_reorderable(session, True)
        self.empty.hide()
        self.notebook.show_all()
        self.notebook.set_current_page(page)
        if connect:
            getattr(session, self.connect_method)()
        return session

    def close_session(self, session: Gtk.Widget) -> None:
        if session not in self.sessions:
            return
        session.shutdown()
        page = self.notebook.page_num(session)
        if page >= 0:
            self.notebook.remove_page(page)
        self.sessions.remove(session)
        if not self.sessions:
            self.notebook.hide()
            self.empty.show()
        self.emit("status-changed", f"Closed {self.kind} tab.")

    def shutdown(self) -> None:
        for session in list(self.sessions):
            session.shutdown()


class SSHSessionTabs(SessionTabs):
    def __init__(self) -> None:
        super().__init__("SSH", SSHConsoleWidget, "connect_ssh")


class SFTPSessionTabs(SessionTabs):
    def __init__(self) -> None:
        super().__init__("SFTP", SFTPBrowserWidget, "connect_sftp")
