from __future__ import annotations

import os
import posixpath
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Callable

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib, GObject, Gtk

from .models import ConnectionProfile
from .sftp import RemoteEntry, SFTPError, SFTPService, UnknownHostKeyError, safe_local_child


def format_size(size: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


class SFTPBrowserWidget(Gtk.Box):
    __gsignals__ = {"status-changed": (GObject.SignalFlags.RUN_FIRST, None, (str,))}

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.profile: ConnectionProfile | None = None
        self.password = ""
        self.service: SFTPService | None = None
        self.local_dir = Path.home()
        self.remote_dir = "/"
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sftp")
        self.busy = False
        self._build_ui()
        self.refresh_local()

    def _build_ui(self) -> None:
        toolbar = Gtk.Box(spacing=6)
        toolbar.get_style_context().add_class("tool-strip")
        self.pack_start(toolbar, False, False, 0)
        self.action_widgets: list[Gtk.Widget] = []

        self.connect_button = self._button(toolbar, "Connect SFTP", self.connect_sftp, "suggested-action")
        self.disconnect_button = self._button(toolbar, "Disconnect", self.disconnect_sftp)
        self.disconnect_button.set_sensitive(False)
        self._button(toolbar, "Refresh", self.refresh_remote)
        self._button(toolbar, "Upload →", self.upload_selected)
        self._button(toolbar, "← Download", self.download_selected)
        self._button(toolbar, "New Folder", self.create_remote_directory)
        self._button(toolbar, "Rename", self.rename_remote_selected)
        self._button(toolbar, "Delete", self.delete_remote_selected, "destructive-action")

        self.spinner = Gtk.Spinner()
        toolbar.pack_end(self.spinner, False, False, 4)

        pane = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        pane.set_position(550)
        self.pack_start(pane, True, True, 0)

        local_panel, self.local_path_entry, self.local_store, self.local_tree = self._file_panel("THIS COMPUTER")
        pane.pack1(local_panel, True, False)
        self.local_path_entry.connect("activate", self._on_local_path_activate)
        self.local_tree.connect("row-activated", self._on_local_activated)
        self.local_tree.connect("button-press-event", self._on_file_button_press, True)

        remote_panel, self.remote_path_entry, self.remote_store, self.remote_tree = self._file_panel("REMOTE SERVER")
        pane.pack2(remote_panel, True, False)
        self.remote_path_entry.connect("activate", self._on_remote_path_activate)
        self.remote_tree.connect("row-activated", self._on_remote_activated)
        self.remote_tree.connect("button-press-event", self._on_file_button_press, False)

    def _button(self, parent: Gtk.Box, label: str, callback: Callable, style: str = "") -> Gtk.Button:
        button = Gtk.Button(label=label)
        button.connect("clicked", lambda *_: callback())
        if style:
            button.get_style_context().add_class(style)
        parent.pack_start(button, False, False, 0)
        self.action_widgets.append(button)
        return button

    def _file_panel(self, title: str):
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        panel.get_style_context().add_class("file-panel")

        heading = Gtk.Label(label=title)
        heading.set_xalign(0)
        heading.get_style_context().add_class("eyebrow")
        panel.pack_start(heading, False, False, 0)

        path_row = Gtk.Box(spacing=4)
        panel.pack_start(path_row, False, False, 0)
        up = Gtk.Button.new_from_icon_name("go-up-symbolic", Gtk.IconSize.BUTTON)
        path_row.pack_start(up, False, False, 0)
        entry = Gtk.Entry()
        path_row.pack_start(entry, True, True, 0)

        store = Gtk.ListStore(str, str, str, str, bool, object)
        tree = Gtk.TreeView(model=store)
        tree.set_headers_clickable(True)
        tree.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
        tree.append_column(Gtk.TreeViewColumn("Name", Gtk.CellRendererText(), text=0))
        tree.append_column(Gtk.TreeViewColumn("Type", Gtk.CellRendererText(), text=1))
        tree.append_column(Gtk.TreeViewColumn("Size", Gtk.CellRendererText(), text=2))
        tree.append_column(Gtk.TreeViewColumn("Modified", Gtk.CellRendererText(), text=3))
        for column in tree.get_columns():
            column.set_resizable(True)
        tree.get_column(0).set_expand(True)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.add(tree)
        panel.pack_start(scroll, True, True, 0)

        if title == "THIS COMPUTER":
            up.connect("clicked", lambda *_: self.local_up())
        else:
            up.connect("clicked", lambda *_: self.remote_up())
        return panel, entry, store, tree

    def set_profile(self, profile: ConnectionProfile | None, password: str) -> None:
        changed = self.profile is None or profile is None or self.profile.id != profile.id
        if changed:
            self._close_service()
        self.profile = profile
        self.password = password
        self.remote_dir = profile.remote_path if profile else "/"
        self.remote_path_entry.set_text(self.remote_dir)

    def connect_sftp(self) -> None:
        if self.profile is None:
            self._status("Select a server first.")
            return
        errors = self.profile.validate()
        if errors:
            self._status(errors[0])
            return
        self._close_service()
        self.service = SFTPService(self.profile, self.password)

        def connected(_result) -> None:
            self.connect_button.set_sensitive(False)
            self.disconnect_button.set_sensitive(True)
            self.refresh_remote()

        self._run("Connecting SFTP", self.service.connect, connected, self._handle_connect_error)

    def disconnect_sftp(self) -> None:
        self._close_service()
        self.remote_store.clear()
        self.connect_button.set_sensitive(True)
        self.disconnect_button.set_sensitive(False)
        self._status("SFTP disconnected.")

    def refresh_local(self) -> None:
        self.local_store.clear()
        self.local_path_entry.set_text(str(self.local_dir))
        try:
            entries = sorted(os.scandir(self.local_dir), key=lambda item: (not item.is_dir(), item.name.casefold()))
        except OSError as error:
            self._status(f"Cannot open local folder: {error}")
            return
        for item in entries:
            try:
                details = item.stat(follow_symlinks=False)
                is_dir = item.is_dir(follow_symlinks=False)
                self.local_store.append([
                    item.name,
                    "Folder" if is_dir else "File",
                    "" if is_dir else format_size(details.st_size),
                    datetime.fromtimestamp(details.st_mtime).strftime("%Y-%m-%d %H:%M"),
                    is_dir,
                    Path(item.path),
                ])
            except OSError:
                continue

    def refresh_remote(self) -> None:
        if self.service is None:
            self.connect_sftp()
            return

        def loaded(result) -> None:
            actual_path, entries = result
            self.remote_dir = actual_path
            self.remote_path_entry.set_text(actual_path)
            self.remote_store.clear()
            for item in entries:
                self.remote_store.append([
                    item.name,
                    "Folder" if item.is_dir else "File",
                    "" if item.is_dir else format_size(item.size),
                    item.modified.strftime("%Y-%m-%d %H:%M"),
                    item.is_dir,
                    item,
                ])
            self._status(f"SFTP connected. {len(entries)} items in {actual_path}")

        self._run("Loading remote files", lambda: self.service.list_dir(self.remote_dir), loaded)

    def local_up(self) -> None:
        self.local_dir = self.local_dir.parent
        self.refresh_local()

    def remote_up(self) -> None:
        self.remote_dir = posixpath.dirname(self.remote_dir.rstrip("/")) or "/"
        self.refresh_remote()

    def upload_selected(self) -> None:
        paths = self._selected_objects(self.local_tree)
        if not paths:
            self._status("Select one or more local files or folders.")
            return
        if self.service is None:
            self._status("Connect SFTP first.")
            return

        def upload_all() -> None:
            for path in paths:
                self.service.upload(path, self.remote_dir, self._progress)

        self._run(f"Uploading {len(paths)} item(s)", upload_all, lambda _: self.refresh_remote())

    def download_selected(self) -> None:
        entries = self._selected_objects(self.remote_tree)
        if not entries:
            self._status("Select one or more remote files or folders.")
            return
        if self.service is None:
            self._status("Connect SFTP first.")
            return
        try:
            conflicts = [entry for entry in entries if safe_local_child(self.local_dir, entry.name).exists()]
        except SFTPError as error:
            self._status(str(error))
            return
        overwrite = False
        if conflicts:
            dialog = Gtk.MessageDialog(
                transient_for=self.get_toplevel(),
                flags=Gtk.DialogFlags.MODAL,
                message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.CANCEL,
                text=f"Replace or merge {len(conflicts)} existing local item(s)?",
            )
            dialog.format_secondary_text("Existing files with the same names will be overwritten.")
            dialog.add_button("Replace / Merge", Gtk.ResponseType.OK)
            overwrite = dialog.run() == Gtk.ResponseType.OK
            dialog.destroy()
            if not overwrite:
                self._status("Download cancelled; existing local items were left unchanged.")
                return

        def download_all() -> None:
            for entry in entries:
                self.service.download(entry, self.local_dir, self._progress, overwrite=overwrite)

        self._run(f"Downloading {len(entries)} item(s)", download_all, lambda _: self.refresh_local())

    def create_remote_directory(self) -> None:
        name = self._text_dialog("New remote folder", "Folder name")
        if name and self.service:
            self._run("Creating folder", lambda: self.service.mkdir(self.remote_dir, name), lambda _: self.refresh_remote())

    def create_local_directory(self) -> None:
        name = self._text_dialog("New local folder", "Folder name")
        if not name:
            return
        if Path(name).name != name or name in {".", ".."}:
            self._status("Enter a folder name without slashes.")
            return
        try:
            (self.local_dir / name).mkdir()
        except OSError as error:
            self._status(f"Could not create the local folder: {error}")
            return
        self.refresh_local()
        self._status(f"Created local folder {name}.")

    def open_local_selected(self) -> None:
        paths = self._selected_objects(self.local_tree)
        if not paths:
            self._status("Select a local file or folder to open.")
            return
        if len(paths) == 1 and paths[0].is_dir():
            self.local_dir = paths[0].resolve()
            self.refresh_local()
            return
        opened = 0
        for path in paths:
            try:
                Gio.AppInfo.launch_default_for_uri(path.resolve().as_uri(), None)
                opened += 1
            except GLib.Error as error:
                self._status(f"Could not open {path.name}: {error.message}")
                return
        self._status(f"Opened {opened} local file(s) in the default editor/application.")

    def rename_local_selected(self) -> None:
        paths = self._selected_objects(self.local_tree)
        if len(paths) != 1:
            self._status("Select exactly one local item to rename.")
            return
        source = paths[0]
        new_name = self._text_dialog("Rename local item", "New name", source.name)
        if not new_name:
            return
        if Path(new_name).name != new_name or new_name in {".", ".."}:
            self._status("Enter a name without slashes.")
            return
        target = source.with_name(new_name)
        if target.exists():
            self._status(f"A local item named {new_name} already exists.")
            return
        try:
            source.rename(target)
        except OSError as error:
            self._status(f"Could not rename the local item: {error}")
            return
        self.refresh_local()
        self._status(f"Renamed {source.name} to {new_name}.")

    def trash_local_selected(self) -> None:
        paths = self._selected_objects(self.local_tree)
        if not paths:
            self._status("Select local files or folders to move to Trash.")
            return
        dialog = Gtk.MessageDialog(
            transient_for=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.CANCEL,
            text=f"Move {len(paths)} local item(s) to Trash?",
        )
        dialog.add_button("Move to Trash", Gtk.ResponseType.OK).get_style_context().add_class("destructive-action")
        response = dialog.run()
        dialog.destroy()
        if response != Gtk.ResponseType.OK:
            return
        try:
            for path in paths:
                Gio.File.new_for_path(str(path)).trash(None)
        except GLib.Error as error:
            self._status(f"Could not move an item to Trash: {error.message}")
            return
        self.refresh_local()
        self._status(f"Moved {len(paths)} local item(s) to Trash.")

    def rename_remote_selected(self) -> None:
        entries = self._selected_objects(self.remote_tree)
        if len(entries) != 1 or self.service is None:
            self._status("Select exactly one remote item to rename.")
            return
        new_name = self._text_dialog("Rename remote item", "New name", entries[0].name)
        if new_name:
            self._run("Renaming item", lambda: self.service.rename(entries[0], new_name), lambda _: self.refresh_remote())

    def delete_remote_selected(self) -> None:
        entries = self._selected_objects(self.remote_tree)
        if not entries or self.service is None:
            self._status("Select remote files or folders to delete.")
            return
        dialog = Gtk.MessageDialog(
            transient_for=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.CANCEL,
            text=f"Permanently delete {len(entries)} remote item(s)?",
        )
        dialog.format_secondary_text("Folders and everything inside them will be removed. This cannot be undone.")
        dialog.add_button("Delete", Gtk.ResponseType.OK).get_style_context().add_class("destructive-action")
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.OK:
            self._run("Deleting remote items", lambda: self.service.delete(entries), lambda _: self.refresh_remote())

    def shutdown(self) -> None:
        self._close_service()
        self.executor.shutdown(wait=False, cancel_futures=True)

    def _on_local_path_activate(self, entry: Gtk.Entry) -> None:
        candidate = Path(entry.get_text()).expanduser()
        if candidate.is_dir():
            self.local_dir = candidate.resolve()
            self.refresh_local()
        else:
            self._status("That local folder does not exist.")

    def _on_remote_path_activate(self, entry: Gtk.Entry) -> None:
        self.remote_dir = entry.get_text().strip() or "/"
        self.refresh_remote()

    def _on_local_activated(self, _tree, path, _column) -> None:
        row = self.local_store[path]
        if row[4]:
            self.local_dir = row[5]
            self.refresh_local()
        else:
            self.open_local_selected()

    def _on_remote_activated(self, _tree, path, _column) -> None:
        row = self.remote_store[path]
        if row[4]:
            self.remote_dir = row[5].path
            self.refresh_remote()
        else:
            self.download_selected()

    def _on_file_button_press(self, tree: Gtk.TreeView, event: Gdk.EventButton, is_local: bool) -> bool:
        hit = tree.get_path_at_pos(int(event.x), int(event.y))
        selection = tree.get_selection()
        modifiers = event.state & Gtk.accelerator_get_default_mod_mask()

        if event.button == 1 and event.type == Gdk.EventType.DOUBLE_BUTTON_PRESS and hit:
            if is_local:
                self._on_local_activated(tree, hit[0], hit[1])
            else:
                self._on_remote_activated(tree, hit[0], hit[1])
            return True

        if event.button == 1 and event.type == Gdk.EventType.BUTTON_PRESS:
            other_tree = self.remote_tree if is_local else self.local_tree
            other_tree.get_selection().unselect_all()
            if not (modifiers & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK)):
                selection.unselect_all()
                if hit:
                    selection.select_path(hit[0])
                    tree.set_cursor(hit[0], hit[1], False)
                return True
            return False

        if event.button == 3 and event.type == Gdk.EventType.BUTTON_PRESS:
            if hit:
                path = hit[0]
                if not selection.path_is_selected(path):
                    selection.unselect_all()
                    selection.select_path(path)
                    tree.set_cursor(path, hit[1], False)
            else:
                selection.unselect_all()
            menu = self._local_context_menu() if is_local else self._remote_context_menu()
            menu.show_all()
            menu.popup_at_pointer(event)
            return True
        return False

    @staticmethod
    def _menu_item(menu: Gtk.Menu, label: str, callback: Callable, sensitive: bool = True) -> None:
        item = Gtk.MenuItem.new_with_label(label)
        item.set_sensitive(sensitive)
        item.connect("activate", lambda *_: callback())
        menu.append(item)

    def _local_context_menu(self) -> Gtk.Menu:
        menu = Gtk.Menu()
        selected = self._selected_objects(self.local_tree)
        self._menu_item(menu, "Open / Edit", self.open_local_selected, bool(selected))
        self._menu_item(menu, "Upload to Remote", self.upload_selected, bool(selected) and self.service is not None)
        menu.append(Gtk.SeparatorMenuItem())
        self._menu_item(menu, "New Folder", self.create_local_directory)
        self._menu_item(menu, "Rename", self.rename_local_selected, len(selected) == 1)
        self._menu_item(menu, "Move to Trash", self.trash_local_selected, bool(selected))
        menu.append(Gtk.SeparatorMenuItem())
        self._menu_item(menu, "Copy Path", lambda: self._copy_paths(selected), bool(selected))
        self._menu_item(menu, "Refresh", self.refresh_local)
        return menu

    def _remote_context_menu(self) -> Gtk.Menu:
        menu = Gtk.Menu()
        selected = self._selected_objects(self.remote_tree)
        one_directory = len(selected) == 1 and selected[0].is_dir
        self._menu_item(menu, "Open Folder", lambda: self._open_remote_directory(selected[0]), one_directory)
        self._menu_item(menu, "Download to Local", self.download_selected, bool(selected) and self.service is not None)
        menu.append(Gtk.SeparatorMenuItem())
        self._menu_item(menu, "New Folder", self.create_remote_directory, self.service is not None)
        self._menu_item(menu, "Rename", self.rename_remote_selected, len(selected) == 1 and self.service is not None)
        self._menu_item(menu, "Delete Permanently", self.delete_remote_selected, bool(selected) and self.service is not None)
        menu.append(Gtk.SeparatorMenuItem())
        self._menu_item(menu, "Copy Remote Path", lambda: self._copy_paths([item.path for item in selected]), bool(selected))
        self._menu_item(menu, "Refresh", self.refresh_remote, self.service is not None)
        return menu

    def _open_remote_directory(self, entry: RemoteEntry) -> None:
        self.remote_dir = entry.path
        self.refresh_remote()

    def _copy_paths(self, paths: list) -> None:
        text = "\n".join(str(path) for path in paths)
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(text, -1)
        self._status(f"Copied {len(paths)} path(s) to the clipboard.")

    def _selected_objects(self, tree: Gtk.TreeView) -> list:
        model, paths = tree.get_selection().get_selected_rows()
        return [model[path][5] for path in paths]

    def _run(
        self,
        label: str,
        job: Callable,
        on_success: Callable,
        on_error: Callable[[Exception], bool] | None = None,
    ) -> None:
        if self.busy:
            self._status("Please wait for the current SFTP operation.")
            return
        self.busy = True
        self.spinner.start()
        for widget in self.action_widgets:
            widget.set_sensitive(False)
        self._status(f"{label} ...")
        future = self.executor.submit(job)
        future.add_done_callback(lambda completed: GLib.idle_add(self._finish, completed, on_success, on_error))

    def _finish(
        self,
        future: Future,
        on_success: Callable,
        on_error: Callable[[Exception], bool] | None,
    ) -> bool:
        self.busy = False
        self.spinner.stop()
        for widget in self.action_widgets:
            widget.set_sensitive(True)
        self.disconnect_button.set_sensitive(self.service is not None and self.service.connected)
        self.connect_button.set_sensitive(not self.disconnect_button.get_sensitive())
        try:
            result = future.result()
        except (SFTPError, OSError) as error:
            if on_error and on_error(error):
                return False
            self._status(f"SFTP error: {error}")
            return False
        except Exception as error:
            self._status(f"Unexpected SFTP error: {error}")
            return False
        on_success(result)
        return False

    def _handle_connect_error(self, error: Exception) -> bool:
        if not isinstance(error, UnknownHostKeyError) or self.service is None:
            return False
        dialog = Gtk.MessageDialog(
            transient_for=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.CANCEL,
            text=f"Trust the new host key for {error.hostname}?",
        )
        dialog.format_secondary_text(
            f"Algorithm: {error.algorithm}\nFingerprint: {error.fingerprint}\n\n"
            "Verify this fingerprint with the server administrator before continuing."
        )
        dialog.add_button("Trust and Connect", Gtk.ResponseType.OK)
        response = dialog.run()
        dialog.destroy()
        if response != Gtk.ResponseType.OK:
            self._status("SFTP connection cancelled; the unknown host key was not saved.")
            return True
        try:
            self.service.trust_host_key(error)
        except SFTPError as trust_error:
            self._status(str(trust_error))
            return True
        self.connect_sftp()
        return True

    def _progress(self, transferred: int, total: int) -> None:
        if total:
            percent = int(transferred * 100 / total)
            GLib.idle_add(self._status, f"Transferring: {percent}%")

    def _close_service(self) -> None:
        if self.service:
            self.service.close()
        self.service = None

    def _text_dialog(self, title: str, placeholder: str, value: str = "") -> str:
        dialog = Gtk.Dialog(title=title, transient_for=self.get_toplevel(), flags=Gtk.DialogFlags.MODAL)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Save", Gtk.ResponseType.OK)
        entry = Gtk.Entry(text=value)
        entry.set_placeholder_text(placeholder)
        entry.set_activates_default(True)
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.get_content_area().pack_start(entry, True, True, 16)
        dialog.show_all()
        response = dialog.run()
        result = entry.get_text().strip() if response == Gtk.ResponseType.OK else ""
        dialog.destroy()
        return result

    def _status(self, message: str) -> bool:
        self.emit("status-changed", message)
        return False
