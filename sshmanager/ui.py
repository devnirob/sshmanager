from __future__ import annotations

from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, Gtk

from .config import APP_ID, APP_NAME, CONFIG_DIR, VERSION, ensure_app_dirs
from .models import ConnectionProfile
from .profiles import ProfileStore, ProfileStoreError
from .secrets import PasswordStore, PasswordStoreError
from .settings import DEFAULT_THEME, THEME_CHOICES, SettingsStore, SettingsStoreError
from .session_tabs import SFTPSessionTabs, SSHSessionTabs
from .themes import THEME_CSS


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application) -> None:
        super().__init__(application=app, title=APP_NAME)
        self.set_icon_name(APP_ID)
        self.set_default_size(1380, 850)
        self.set_size_request(960, 620)
        ensure_app_dirs()
        self.profile_store = ProfileStore()
        self.password_store = PasswordStore()
        self.settings_store = SettingsStore()
        self.settings = self.settings_store.load()
        self.startup_warning = ""
        self.profiles = self._load_profiles()
        self.current_profile_id = self.profiles[0].id
        self._install_css()
        self._build_ui()
        self._refresh_profile_list(self.current_profile_id)
        self._load_profile(self.current_profile())
        if self.startup_warning:
            self._set_status(self.startup_warning)
        self.connect("delete-event", self._on_close)

    def _load_profiles(self) -> list[ConnectionProfile]:
        try:
            profiles = self.profile_store.load()
        except ProfileStoreError as error:
            # Keep a malformed profile file untouched so the user can recover it.
            self.startup_warning = str(error)
            return [ConnectionProfile.create("Recovered session")]
        if not profiles:
            profiles = [ConnectionProfile.create("My server")]
            self.profile_store.save(profiles)
        return profiles

    def _install_css(self) -> None:
        self.css_provider = Gtk.CssProvider()
        self.css_provider.load_from_data(THEME_CSS.get(self.settings.theme, THEME_CSS[DEFAULT_THEME]))
        Gtk.StyleContext.add_provider_for_screen(
            self.get_screen(), self.css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _build_ui(self) -> None:
        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.props.title = APP_NAME
        header.props.subtitle = f"SSH + SFTP workspace  {VERSION}"
        self.set_titlebar(header)
        settings_button = Gtk.Button.new_from_icon_name("preferences-system-symbolic", Gtk.IconSize.BUTTON)
        settings_button.set_tooltip_text("Appearance settings")
        settings_button.connect("clicked", self._open_settings)
        header.pack_end(settings_button)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(root)
        body = Gtk.Box()
        root.pack_start(body, True, True, 0)

        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        sidebar.set_size_request(295, -1)
        sidebar.get_style_context().add_class("sidebar")
        body.pack_start(sidebar, False, False, 0)

        brand = Gtk.Label(label="Server Library")
        brand.set_xalign(0)
        brand.get_style_context().add_class("brand")
        sidebar.pack_start(brand, False, False, 0)
        sub = Gtk.Label(label="Your saved Linux hosts")
        sub.set_xalign(0)
        sub.get_style_context().add_class("muted-light")
        sidebar.pack_start(sub, False, False, 0)

        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Find a server")
        self.search_entry.connect("search-changed", lambda *_: self._refresh_profile_list(self.current_profile_id))
        sidebar.pack_start(self.search_entry, False, False, 4)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sidebar.pack_start(scroll, True, True, 0)
        self.profile_list = Gtk.ListBox()
        self.profile_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.profile_list.connect("row-selected", self._on_profile_selected)
        scroll.add(self.profile_list)

        sidebar_actions = Gtk.Box(spacing=6)
        sidebar.pack_start(sidebar_actions, False, False, 0)
        self._side_button(sidebar_actions, "New", self._new_profile)
        self._side_button(sidebar_actions, "Duplicate", self._duplicate_profile)
        self._side_button(sidebar_actions, "Delete", self._delete_profile)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        body.pack_start(content, True, True, 0)

        summary = Gtk.Box(spacing=12)
        summary.get_style_context().add_class("content-pad")
        content.pack_start(summary, False, False, 0)
        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        summary.pack_start(labels, True, True, 0)
        self.server_title = Gtk.Label()
        self.server_title.set_xalign(0)
        self.server_title.get_style_context().add_class("server-title")
        labels.pack_start(self.server_title, False, False, 0)
        self.server_subtitle = Gtk.Label()
        self.server_subtitle.set_xalign(0)
        labels.pack_start(self.server_subtitle, False, False, 0)

        terminal_quick = Gtk.Button(label="Open SSH")
        terminal_quick.get_style_context().add_class("suggested-action")
        terminal_quick.connect("clicked", self._quick_terminal)
        summary.pack_start(terminal_quick, False, False, 0)
        files_quick = Gtk.Button(label="Browse Files")
        files_quick.connect("clicked", self._quick_files)
        summary.pack_start(files_quick, False, False, 0)

        self.notebook = Gtk.Notebook()
        content.pack_start(self.notebook, True, True, 0)
        self.notebook.append_page(self._build_profile_page(), Gtk.Label(label="SERVER DETAILS"))
        self.ssh_sessions = SSHSessionTabs()
        self.ssh_sessions.set_theme(self.settings.theme)
        self.ssh_sessions.connect("new-tab-requested", self._open_new_session)
        self.ssh_sessions.connect("status-changed", self._on_tool_status)
        self.notebook.append_page(self.ssh_sessions, Gtk.Label(label="SSH TERMINALS"))
        self.sftp_sessions = SFTPSessionTabs()
        self.sftp_sessions.connect("new-tab-requested", self._open_new_session)
        self.sftp_sessions.connect("status-changed", self._on_tool_status)
        self.notebook.append_page(self.sftp_sessions, Gtk.Label(label="SFTP SESSIONS"))

        self.status = Gtk.Label(label="Ready")
        self.status.set_xalign(0)
        self.status.get_style_context().add_class("statusbar")
        root.pack_start(self.status, False, False, 0)

    def _open_settings(self, _button) -> None:
        dialog = Gtk.Dialog(
            title="Appearance",
            transient_for=self,
            flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
        )
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Apply", Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.set_resizable(False)

        content = dialog.get_content_area()
        content.set_border_width(20)
        content.set_spacing(12)
        title = Gtk.Label()
        title.set_markup("<span size='large' weight='bold'>Choose an application theme</span>")
        title.set_xalign(0)
        content.pack_start(title, False, False, 0)
        detail = Gtk.Label(
            label="VS Code Dark is optimized for long terminal sessions. System follows your desktop colors."
        )
        detail.set_xalign(0)
        detail.set_line_wrap(True)
        content.pack_start(detail, False, False, 0)

        theme_row = Gtk.Box(spacing=14)
        theme_label = Gtk.Label(label="Color theme")
        theme_label.set_xalign(0)
        theme_row.pack_start(theme_label, True, True, 0)
        theme_combo = Gtk.ComboBoxText()
        for theme_id, label in THEME_CHOICES:
            theme_combo.append(theme_id, label)
        theme_combo.set_active_id(self.settings.theme)
        theme_row.pack_end(theme_combo, False, False, 0)
        content.pack_start(theme_row, False, False, 4)

        dialog.show_all()
        response = dialog.run()
        selected_theme = theme_combo.get_active_id()
        dialog.destroy()
        if response != Gtk.ResponseType.OK or not selected_theme:
            return

        self.settings.theme = selected_theme
        self._apply_theme(selected_theme)
        try:
            self.settings_store.save(self.settings)
        except SettingsStoreError as error:
            self._set_status(str(error))
            return
        selected_label = next(label for theme_id, label in THEME_CHOICES if theme_id == selected_theme)
        self._set_status(f"Theme changed to {selected_label}.")

    def _apply_theme(self, theme_name: str) -> None:
        css = THEME_CSS.get(theme_name, THEME_CSS[DEFAULT_THEME])
        self.css_provider.load_from_data(css)
        self.ssh_sessions.set_theme(theme_name)

    def _build_profile_page(self) -> Gtk.Widget:
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.get_style_context().add_class("content-pad")
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        card.get_style_context().add_class("profile-card")
        outer.pack_start(card, True, True, 0)

        intro = Gtk.Label(label="CONNECTION SETTINGS")
        intro.set_xalign(0)
        intro.get_style_context().add_class("eyebrow")
        card.pack_start(intro, False, False, 0)

        grid = Gtk.Grid(column_spacing=16, row_spacing=12)
        grid.set_column_homogeneous(True)
        card.pack_start(grid, False, False, 0)
        self.name_entry = self._field(grid, "Connection name", 0, 0)
        self.host_entry = self._field(grid, "Host / IP", 1, 0)
        self.username_entry = self._field(grid, "Username", 0, 1)
        self.port_entry = self._field(grid, "Port", 1, 1)
        self.password_entry = self._field(grid, "Password", 0, 2)
        self.password_entry.set_visibility(False)
        self.password_entry.set_max_length(4096)
        self.remote_entry = self._field(grid, "Starting remote folder", 1, 2)
        self.key_entry = self._field(grid, "Private key path (optional)", 0, 3)
        self.jump_entry = self._field(grid, "Jump host (optional)", 1, 3)

        options = Gtk.Box(spacing=18)
        card.pack_start(options, False, False, 0)
        self.save_password = Gtk.CheckButton(label="Save password in Linux keyring")
        options.pack_start(self.save_password, False, False, 0)
        self.use_agent = Gtk.CheckButton(label="Use SSH agent and keys from ~/.ssh")
        options.pack_start(self.use_agent, False, False, 0)
        reveal = Gtk.CheckButton(label="Show password")
        reveal.connect("toggled", lambda button: self.password_entry.set_visibility(button.get_active()))
        options.pack_end(reveal, False, False, 0)

        notes_label = Gtk.Label(label="NOTES")
        notes_label.set_xalign(0)
        notes_label.get_style_context().add_class("eyebrow")
        card.pack_start(notes_label, False, False, 0)
        notes_scroll = Gtk.ScrolledWindow()
        notes_scroll.set_min_content_height(100)
        card.pack_start(notes_scroll, True, True, 0)
        self.notes = Gtk.TextView()
        self.notes.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        notes_scroll.add(self.notes)

        actions = Gtk.Box(spacing=8)
        card.pack_start(actions, False, False, 0)
        save = Gtk.Button(label="Save Server")
        save.get_style_context().add_class("suggested-action")
        save.connect("clicked", self._save_clicked)
        actions.pack_start(save, False, False, 0)
        key_picker = Gtk.Button(label="Choose Private Key")
        key_picker.connect("clicked", self._choose_key)
        actions.pack_start(key_picker, False, False, 0)
        config = Gtk.Button(label="Open App Data")
        config.connect("clicked", self._open_config)
        actions.pack_end(config, False, False, 0)
        return outer

    def _field(self, grid: Gtk.Grid, title: str, column: int, row: int) -> Gtk.Entry:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        label = Gtk.Label(label=title)
        label.set_xalign(0)
        entry = Gtk.Entry()
        box.pack_start(label, False, False, 0)
        box.pack_start(entry, False, False, 0)
        grid.attach(box, column, row, 1, 1)
        return entry

    def _side_button(self, parent: Gtk.Box, label: str, callback) -> None:
        button = Gtk.Button(label=label)
        button.connect("clicked", callback)
        parent.pack_start(button, True, True, 0)

    def _new_profile(self, _button) -> None:
        profile = ConnectionProfile.create()
        self.profiles.append(profile)
        self.profile_store.save(self.profiles)
        self.current_profile_id = profile.id
        self._refresh_profile_list(profile.id)
        self._load_profile(profile)
        self._set_status("New server profile created.")

    def _duplicate_profile(self, _button) -> None:
        original = self.current_profile()
        duplicate = ConnectionProfile.from_dict(original.to_dict())
        duplicate.id = ConnectionProfile.create().id
        duplicate.name = f"{original.name} copy"
        self.profiles.append(duplicate)
        try:
            password = self.password_store.load(original.id)
            if password and duplicate.save_password:
                self.password_store.save(duplicate.id, password)
        except PasswordStoreError:
            pass
        self.profile_store.save(self.profiles)
        self.current_profile_id = duplicate.id
        self._refresh_profile_list(duplicate.id)
        self._load_profile(duplicate)

    def _delete_profile(self, _button) -> None:
        profile = self.current_profile()
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.CANCEL,
            text=f"Delete {profile.name}?",
        )
        dialog.add_button("Delete", Gtk.ResponseType.OK)
        response = dialog.run()
        dialog.destroy()
        if response != Gtk.ResponseType.OK:
            return
        try:
            self.password_store.clear(profile.id)
        except PasswordStoreError:
            pass
        self.profiles = [item for item in self.profiles if item.id != profile.id]
        if not self.profiles:
            self.profiles.append(ConnectionProfile.create("My server"))
        self.current_profile_id = self.profiles[0].id
        self.profile_store.save(self.profiles)
        self._refresh_profile_list(self.current_profile_id)
        self._load_profile(self.current_profile())

    def _save_clicked(self, _button) -> None:
        if self._save_form():
            self._set_status(f"Saved {self.current_profile().name}.")

    def _save_form(self) -> bool:
        profile = self.current_profile()
        candidate = ConnectionProfile.from_dict(profile.to_dict())
        try:
            port = int(self.port_entry.get_text().strip())
        except ValueError:
            self._show_error("Invalid port", "Port must be a number between 1 and 65535.")
            return False
        candidate.name = self.name_entry.get_text().strip()
        candidate.host = self.host_entry.get_text().strip()
        candidate.username = self.username_entry.get_text().strip()
        candidate.port = port
        candidate.remote_path = self.remote_entry.get_text().strip() or "/"
        candidate.key_path = self.key_entry.get_text().strip()
        candidate.jump_host = self.jump_entry.get_text().strip()
        candidate.save_password = self.save_password.get_active()
        candidate.use_agent = self.use_agent.get_active()
        buffer = self.notes.get_buffer()
        candidate.notes = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True).strip()
        errors = candidate.validate()
        if errors:
            self._show_error("Cannot save server", "\n".join(errors))
            return False
        entered_password = self.password_entry.get_text()
        updated_profiles = [candidate if item.id == candidate.id else item for item in self.profiles]
        try:
            if candidate.save_password:
                self.password_store.save(candidate.id, entered_password)
            else:
                self.password_store.clear(candidate.id)
            self.profile_store.save(updated_profiles)
        except (PasswordStoreError, ProfileStoreError) as error:
            self._show_error("Could not save", str(error))
            return False
        self.profiles = updated_profiles
        self._refresh_profile_list(candidate.id)
        # An unsaved password remains usable for tabs opened in this app run.
        self._sync_tools(candidate, entered_password)
        self._update_summary(candidate)
        return True

    def _on_profile_selected(self, _listbox, row) -> None:
        if row is None or not hasattr(row, "profile_id"):
            return
        self.current_profile_id = row.profile_id
        self._load_profile(self.current_profile())

    def _load_profile(self, profile: ConnectionProfile) -> None:
        self.name_entry.set_text(profile.name)
        self.host_entry.set_text(profile.host)
        self.username_entry.set_text(profile.username)
        self.port_entry.set_text(str(profile.port))
        self.remote_entry.set_text(profile.remote_path)
        self.key_entry.set_text(profile.key_path)
        self.jump_entry.set_text(profile.jump_host)
        self.save_password.set_active(profile.save_password)
        self.use_agent.set_active(profile.use_agent)
        self.notes.get_buffer().set_text(profile.notes)
        try:
            password = self.password_store.load(profile.id) if profile.save_password else ""
        except PasswordStoreError as error:
            password = ""
            self._set_status(str(error))
        self.password_entry.set_text(password)
        self._sync_tools(profile, password)
        self._update_summary(profile)

    def _sync_tools(self, profile: ConnectionProfile, password: str | None = None) -> None:
        if password is None:
            try:
                password = self.password_store.load(profile.id) if profile.save_password else ""
            except PasswordStoreError:
                password = ""
        self.ssh_sessions.set_profile(profile, password)
        self.sftp_sessions.set_profile(profile, password)

    def _update_summary(self, profile: ConnectionProfile) -> None:
        self.server_title.set_text(profile.name or "Unnamed server")
        details = f"{profile.target}:{profile.port}" if profile.host else "Add host, username, and authentication details below"
        self.server_subtitle.set_text(details)

    def _refresh_profile_list(self, select_id: str | None = None) -> None:
        query = self.search_entry.get_text().casefold() if hasattr(self, "search_entry") else ""
        for child in self.profile_list.get_children():
            self.profile_list.remove(child)
        for profile in self.profiles:
            haystack = f"{profile.name} {profile.host} {profile.username}".casefold()
            if query and query not in haystack:
                continue
            row = Gtk.ListBoxRow()
            row.profile_id = profile.id
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            box.set_border_width(10)
            title = Gtk.Label(label=profile.name or "Unnamed server")
            title.set_xalign(0)
            box.pack_start(title, False, False, 0)
            address = Gtk.Label(label=f"{profile.host}:{profile.port}" if profile.host else "Not configured")
            address.set_xalign(0)
            address.get_style_context().add_class("muted-light")
            box.pack_start(address, False, False, 0)
            row.add(box)
            self.profile_list.add(row)
            if profile.id == (select_id or self.current_profile_id):
                self.profile_list.select_row(row)
        self.profile_list.show_all()

    def _quick_terminal(self, _button) -> None:
        if self._save_form():
            self.notebook.set_current_page(1)
            self.ssh_sessions.open_session(connect=True)

    def _quick_files(self, _button) -> None:
        if self._save_form():
            self.notebook.set_current_page(2)
            self.sftp_sessions.open_session(connect=True)

    def _open_new_session(self, sessions) -> None:
        if self._save_form():
            sessions.open_session(connect=True)

    def _choose_key(self, _button) -> None:
        dialog = Gtk.FileChooserDialog(
            title="Choose SSH private key",
            transient_for=self,
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Choose", Gtk.ResponseType.OK)
        dialog.set_current_folder(str(Path.home() / ".ssh"))
        if dialog.run() == Gtk.ResponseType.OK:
            self.key_entry.set_text(dialog.get_filename())
        dialog.destroy()

    def _open_config(self, _button) -> None:
        Gtk.show_uri_on_window(self, Gio.File.new_for_path(str(CONFIG_DIR)).get_uri(), Gtk.get_current_event_time())

    def _on_tool_status(self, _widget, message: str) -> None:
        self._set_status(message)

    def current_profile(self) -> ConnectionProfile:
        return next((item for item in self.profiles if item.id == self.current_profile_id), self.profiles[0])

    def _show_error(self, title: str, message: str) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.CLOSE,
            text=title,
        )
        dialog.format_secondary_text(message)
        dialog.run()
        dialog.destroy()

    def _set_status(self, message: str) -> None:
        self.status.set_text(message)

    def _on_close(self, *_args) -> bool:
        self.ssh_sessions.shutdown()
        self.sftp_sessions.shutdown()
        return False
