from __future__ import annotations

import os
import signal

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Vte", "2.91")
from gi.repository import Gdk, GLib, GObject, Gtk, Pango, Vte

from .models import ConnectionProfile
from .system_ssh import ssh_command
from .themes import TERMINAL_THEMES

PASSWORD_CHILD_FD = 9


def _password_fd_setup(source_fd: int):
    """Return the minimal child setup needed to expose the password pipe."""

    def setup(_user_data: object) -> None:
        if source_fd == PASSWORD_CHILD_FD:
            os.set_inheritable(PASSWORD_CHILD_FD, True)
        else:
            os.dup2(source_fd, PASSWORD_CHILD_FD, inheritable=True)

    return setup


def ssh_exit_message(status: int) -> str:
    """Translate VTE's wait status into an actionable, human-readable result."""
    try:
        exit_code = os.waitstatus_to_exitcode(status)
    except ValueError:
        exit_code = status
    if exit_code == 0:
        return "SSH session ended."
    if exit_code == 5:
        return "SSH authentication failed. Check the saved password and try again."
    if exit_code < 0:
        return f"SSH session was stopped by signal {-exit_code}."
    return f"SSH session ended with exit code {exit_code}."


class SSHConsoleWidget(Gtk.Box):
    __gsignals__ = {"status-changed": (GObject.SignalFlags.RUN_FIRST, None, (str,))}

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.profile: ConnectionProfile | None = None
        self.password = ""
        self.child_pid: int | None = None
        self.theme_name = "vscode-dark"
        self._build_ui()

    def _build_ui(self) -> None:
        toolbar = Gtk.Box(spacing=6)
        toolbar.get_style_context().add_class("tool-strip")
        self.pack_start(toolbar, False, False, 0)

        self.connect_button = Gtk.Button(label="Connect")
        self.connect_button.get_style_context().add_class("suggested-action")
        self.connect_button.connect("clicked", lambda *_: self.connect_ssh())
        toolbar.pack_start(self.connect_button, False, False, 0)

        self.disconnect_button = Gtk.Button(label="Disconnect")
        self.disconnect_button.set_sensitive(False)
        self.disconnect_button.connect("clicked", lambda *_: self.disconnect_ssh())
        toolbar.pack_start(self.disconnect_button, False, False, 0)

        copy_button = Gtk.Button(label="Copy")
        copy_button.set_tooltip_text("Copy selected text (Ctrl+Shift+C)")
        copy_button.connect("clicked", lambda *_: self.copy_selection())
        toolbar.pack_start(copy_button, False, False, 0)

        paste_button = Gtk.Button(label="Paste")
        paste_button.set_tooltip_text("Paste clipboard text (Ctrl+Shift+V)")
        paste_button.connect("clicked", lambda *_: self.paste_clipboard())
        toolbar.pack_start(paste_button, False, False, 0)

        clear_button = Gtk.Button(label="Clear")
        clear_button.connect("clicked", lambda *_: self.terminal.reset(True, True))
        toolbar.pack_start(clear_button, False, False, 0)

        native_button = Gtk.Button(label="Open Separate Terminal")
        native_button.connect("clicked", lambda *_: self.open_native_terminal())
        toolbar.pack_end(native_button, False, False, 0)

        self.terminal = Vte.Terminal()
        self.terminal.set_hexpand(True)
        self.terminal.set_vexpand(True)
        self.terminal.set_scrollback_lines(20000)
        self.terminal.set_scroll_on_output(False)
        self.terminal.set_scroll_on_keystroke(True)
        self.terminal.set_mouse_autohide(True)
        self.terminal.set_font(Pango.FontDescription("Hack 10.5"))
        self.terminal.connect("child-exited", self._on_child_exited)
        self.terminal.connect("key-press-event", self._on_terminal_key_press)
        self.pack_start(self.terminal, True, True, 0)

        self._write_banner("Choose a saved server and press Connect.")

    def set_theme(self, theme_name: str) -> None:
        self.theme_name = theme_name
        theme = TERMINAL_THEMES.get(theme_name, TERMINAL_THEMES["vscode-dark"])

        def color(value: str) -> Gdk.RGBA:
            rgba = Gdk.RGBA()
            rgba.parse(value)
            return rgba

        foreground = color(theme["foreground"])
        background = color(theme["background"])
        palette = [color(value) for value in theme["palette"]]
        self.terminal.set_colors(foreground, background, palette)
        self.terminal.set_color_cursor(color(theme["cursor"]))
        self.terminal.set_color_highlight(color(theme["highlight"]))

    def copy_selection(self) -> None:
        if self.terminal.get_has_selection():
            self.terminal.copy_clipboard_format(Vte.Format.TEXT)

    def paste_clipboard(self) -> None:
        self.terminal.paste_clipboard()

    def _on_terminal_key_press(self, _terminal: Vte.Terminal, event: Gdk.EventKey) -> bool:
        modifiers = event.state & Gtk.accelerator_get_default_mod_mask()
        copy_paste_modifiers = Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK
        if modifiers != copy_paste_modifiers:
            return False
        key = Gdk.keyval_to_lower(event.keyval)
        if key == Gdk.KEY_c:
            self.copy_selection()
            return True
        if key == Gdk.KEY_v:
            self.paste_clipboard()
            return True
        return False

    def set_profile(self, profile: ConnectionProfile | None, password: str) -> None:
        self.profile = profile
        self.password = password

    def connect_ssh(self) -> None:
        if self.child_pid is not None:
            self._status("A terminal session is already open.")
            return
        if self.profile is None:
            self._status("Select a server first.")
            return
        errors = self.profile.validate()
        if errors:
            self._status(errors[0])
            return

        password_fd: int | None = None
        child_setup = None
        if self.password:
            password_fd, password_writer = os.pipe()
            try:
                os.write(password_writer, self.password.encode("utf-8"))
            finally:
                os.close(password_writer)
            child_setup = _password_fd_setup(password_fd)
        command, environment = ssh_command(
            self.profile,
            self.password,
            PASSWORD_CHILD_FD if password_fd is not None else None,
        )
        self.terminal.reset(True, True)
        self._write_banner(f"Connecting to {self.profile.target}:{self.profile.port} ...")
        self.connect_button.set_sensitive(False)
        self.disconnect_button.set_sensitive(True)
        try:
            success, pid = self.terminal.spawn_sync(
                Vte.PtyFlags.DEFAULT,
                str(os.path.expanduser("~")),
                command,
                environment,
                GLib.SpawnFlags.SEARCH_PATH,
                child_setup,
                None,
                None,
            )
        except GLib.Error as error:
            self._write_banner(f"Could not start SSH: {error.message}")
            self._set_disconnected()
            self._status(f"Could not start SSH: {error.message}")
            return
        finally:
            if password_fd is not None:
                os.close(password_fd)
        if not success:
            self._set_disconnected()
            self._status("VTE could not create the SSH process.")
            return
        self.child_pid = pid
        self.terminal.grab_focus()
        self._status(f"Connected terminal for {self.profile.name}.")

    def disconnect_ssh(self) -> None:
        if self.child_pid is not None:
            try:
                process_group = os.getpgid(self.child_pid)
                if process_group != os.getpgrp():
                    os.killpg(process_group, signal.SIGHUP)
                else:
                    os.kill(self.child_pid, signal.SIGHUP)
            except ProcessLookupError:
                pass
        self._set_disconnected()
        self._status("SSH session disconnected.")

    def open_native_terminal(self) -> None:
        if self.profile is None or self.profile.validate():
            self._status("Save valid server details first.")
            return
        window = Gtk.Window(title=f"{self.profile.name} — SSH Manager")
        window.set_default_size(960, 620)
        parent = self.get_toplevel()
        if isinstance(parent, Gtk.Window):
            window.set_transient_for(parent)
            window.set_destroy_with_parent(True)
        console = SSHConsoleWidget()
        console.set_profile(ConnectionProfile.from_dict(self.profile.to_dict()), self.password)
        console.set_theme(self.theme_name)
        console.connect("status-changed", lambda _widget, message: self._status(message))
        window.add(console)

        def close_window(*_args) -> bool:
            console.shutdown()
            return False

        window.connect("delete-event", close_window)
        window.show_all()
        console.connect_ssh()
        self._status(f"Opened a separate SSH window for {self.profile.name}.")

    def shutdown(self) -> None:
        self.disconnect_ssh()

    def _on_child_exited(self, _terminal: Vte.Terminal, status: int) -> None:
        self._set_disconnected()
        self._status(ssh_exit_message(status))

    def _set_disconnected(self) -> None:
        self.child_pid = None
        self.connect_button.set_sensitive(True)
        self.disconnect_button.set_sensitive(False)

    def _write_banner(self, message: str) -> None:
        self.terminal.feed(f"\r\n\x1b[1;38;5;81mSSH Manager\x1b[0m  {message}\r\n\r\n".encode())

    def _status(self, message: str) -> None:
        self.emit("status-changed", message)
