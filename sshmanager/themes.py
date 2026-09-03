from __future__ import annotations


SYSTEM_CSS = b"""
window { background-color: @theme_bg_color; color: @theme_fg_color; }
headerbar { box-shadow: none; }
.sidebar { background-color: shade(@theme_bg_color, 0.88); padding: 18px; border-right: 1px solid @borders; }
.sidebar list { background-color: transparent; }
.sidebar row { border-radius: 6px; margin: 2px 0; }
.sidebar row:selected { background-color: @theme_selected_bg_color; color: @theme_selected_fg_color; }
.brand { font-size: 22px; font-weight: bold; }
.muted-light { opacity: 0.70; }
.server-title { font-size: 24px; font-weight: bold; }
.eyebrow { font-size: 10px; font-weight: bold; letter-spacing: 1.2px; opacity: 0.72; }
.content-pad { padding: 18px; }
.profile-card { background-color: @theme_base_color; border: 1px solid @borders; border-radius: 8px; padding: 22px; }
.tool-strip { background-color: shade(@theme_bg_color, 0.96); border-bottom: 1px solid @borders; padding: 8px; }
.session-strip { background-color: shade(@theme_bg_color, 0.92); border-bottom: 1px solid @borders; padding: 8px; }
.empty-state { opacity: 0.68; font-size: 16px; }
.file-panel { background-color: @theme_base_color; padding: 12px; }
.statusbar { background-color: shade(@theme_bg_color, 0.88); border-top: 1px solid @borders; padding: 7px 12px; }
button.suggested-action { background-image: none; background-color: @theme_selected_bg_color; border-color: @theme_selected_bg_color; color: @theme_selected_fg_color; }
button.destructive-action { background-image: none; background-color: #c72e3b; border-color: #c72e3b; color: white; }
"""


VSCODE_DARK_CSS = b"""
window, .background { background-color: #1e1e1e; color: #cccccc; }
headerbar {
  background-image: none;
  background-color: #181818;
  color: #f0f0f0;
  border-bottom: 1px solid #2b2b2b;
  box-shadow: none;
}
headerbar button {
  background-image: none;
  background-color: transparent;
  color: #cccccc;
  border-color: transparent;
}
headerbar button:hover { background-color: #2a2d2e; color: white; }
.sidebar {
  background-color: #181818;
  color: #cccccc;
  padding: 18px;
  border-right: 1px solid #2b2b2b;
}
.sidebar list { background-color: transparent; color: #cccccc; }
.sidebar row { border-radius: 6px; margin: 2px 0; }
.sidebar row:hover { background-color: #2a2d2e; }
.sidebar row:selected { background-color: #37373d; color: white; }
.sidebar entry {
  background-image: none;
  background-color: #242424;
  color: #f0f0f0;
  border: 1px solid #3c3c3c;
}
.sidebar entry:focus { border-color: #007acc; }
.brand { font-size: 22px; font-weight: bold; color: #f0f0f0; }
.muted-light { color: #9d9d9d; }
.server-title { font-size: 24px; font-weight: bold; color: #f0f0f0; }
.eyebrow { font-size: 10px; font-weight: bold; letter-spacing: 1.2px; color: #9d9d9d; }
.content-pad { padding: 18px; }
.profile-card {
  background-color: #252526;
  border: 1px solid #3c3c3c;
  border-radius: 8px;
  padding: 22px;
}
.tool-strip { background-color: #252526; border-bottom: 1px solid #3c3c3c; padding: 8px; }
.session-strip { background-color: #181818; border-bottom: 1px solid #3c3c3c; padding: 8px; }
.empty-state { color: #9d9d9d; font-size: 16px; }
.file-panel { background-color: #1e1e1e; padding: 12px; }
.statusbar { background-color: #007acc; color: white; padding: 7px 12px; }
entry, textview text {
  background-color: #1e1e1e;
  color: #d4d4d4;
  border-color: #3c3c3c;
}
entry:focus { border-color: #007acc; }
textview { border: 1px solid #3c3c3c; }
button {
  background-image: none;
  background-color: #333333;
  color: #e5e5e5;
  border-color: #4a4a4a;
}
button:hover { background-color: #3e3e42; border-color: #5a5a5a; }
button:disabled { color: #777777; background-color: #2a2a2a; }
button.suggested-action {
  background-image: none;
  background-color: #0e639c;
  border-color: #0e639c;
  color: white;
}
button.suggested-action:hover { background-color: #1177bb; }
button.destructive-action {
  background-image: none;
  background-color: #a1260d;
  border-color: #a1260d;
  color: white;
}
notebook { background-color: #1e1e1e; }
notebook > header { background-color: #181818; border-color: #2b2b2b; }
notebook > header tab { color: #9d9d9d; border: 0; padding: 7px 14px; }
notebook > header tab:checked { color: white; box-shadow: inset 0 -2px #007acc; }
treeview.view { background-color: #1e1e1e; color: #cccccc; }
treeview.view:selected { background-color: #094771; color: white; }
treeview header button { background-color: #252526; border-color: #3c3c3c; color: #cccccc; }
scrollbar trough { background-color: #1e1e1e; }
scrollbar slider { background-color: #4f4f4f; min-width: 10px; min-height: 10px; }
separator { background-color: #3c3c3c; }
"""


LIGHT_CSS = b"""
window, .background { background-color: #f3f3f3; color: #242424; }
headerbar {
  background-image: none;
  background-color: #ffffff;
  color: #242424;
  border-bottom: 1px solid #d4d4d4;
  box-shadow: none;
}
.sidebar { background-color: #f7f7f7; color: #242424; padding: 18px; border-right: 1px solid #d4d4d4; }
.sidebar list { background-color: transparent; color: #242424; }
.sidebar row { border-radius: 6px; margin: 2px 0; }
.sidebar row:hover { background-color: #e8e8e8; }
.sidebar row:selected { background-color: #e4e6f1; color: #242424; }
.brand { font-size: 22px; font-weight: bold; color: #1f1f1f; }
.muted-light { color: #616161; }
.server-title { font-size: 24px; font-weight: bold; color: #1f1f1f; }
.eyebrow { font-size: 10px; font-weight: bold; letter-spacing: 1.2px; color: #616161; }
.content-pad { padding: 18px; }
.profile-card { background-color: white; border: 1px solid #d4d4d4; border-radius: 8px; padding: 22px; }
.tool-strip { background-color: #f3f3f3; border-bottom: 1px solid #d4d4d4; padding: 8px; }
.session-strip { background-color: #ffffff; border-bottom: 1px solid #d4d4d4; padding: 8px; }
.empty-state { color: #616161; font-size: 16px; }
.file-panel { background-color: white; padding: 12px; }
.statusbar { background-color: #007acc; color: white; padding: 7px 12px; }
entry, textview text { background-color: white; color: #242424; border-color: #cecece; }
entry:focus { border-color: #007acc; }
textview { border: 1px solid #cecece; }
button { background-image: none; background-color: #ffffff; color: #242424; border-color: #c8c8c8; }
button:hover { background-color: #e8e8e8; }
button.suggested-action { background-image: none; background-color: #0e639c; border-color: #0e639c; color: white; }
button.suggested-action:hover { background-color: #1177bb; }
button.destructive-action { background-image: none; background-color: #c72e3b; border-color: #c72e3b; color: white; }
notebook > header { background-color: #f3f3f3; border-color: #d4d4d4; }
notebook > header tab { color: #616161; border: 0; padding: 7px 14px; }
notebook > header tab:checked { color: #242424; box-shadow: inset 0 -2px #007acc; }
treeview.view { background-color: white; color: #242424; }
treeview.view:selected { background-color: #add6ff; color: #242424; }
treeview header button { background-color: #f3f3f3; border-color: #d4d4d4; color: #242424; }
"""


THEME_CSS = {
    "system": SYSTEM_CSS,
    "vscode-dark": VSCODE_DARK_CSS,
    "light": LIGHT_CSS,
}


TERMINAL_THEMES = {
    "vscode-dark": {
        "foreground": "#d4d4d4",
        "background": "#1e1e1e",
        "cursor": "#f0f0f0",
        "highlight": "#264f78",
        "palette": (
            "#000000", "#cd3131", "#0dbc79", "#e5e510",
            "#2472c8", "#bc3fbc", "#11a8cd", "#e5e5e5",
            "#666666", "#f14c4c", "#23d18b", "#f5f543",
            "#3b8eea", "#d670d6", "#29b8db", "#e5e5e5",
        ),
    },
    "light": {
        "foreground": "#242424",
        "background": "#ffffff",
        "cursor": "#242424",
        "highlight": "#add6ff",
        "palette": (
            "#000000", "#cd3131", "#00bc00", "#949800",
            "#0451a5", "#bc05bc", "#0598bc", "#555555",
            "#666666", "#cd3131", "#14ce14", "#b5ba00",
            "#0451a5", "#bc05bc", "#0598bc", "#a5a5a5",
        ),
    },
    "system": {
        "foreground": "#d4d4d4",
        "background": "#1e1e1e",
        "cursor": "#f0f0f0",
        "highlight": "#264f78",
        "palette": (
            "#000000", "#cd3131", "#0dbc79", "#e5e510",
            "#2472c8", "#bc3fbc", "#11a8cd", "#e5e5e5",
            "#666666", "#f14c4c", "#23d18b", "#f5f543",
            "#3b8eea", "#d670d6", "#29b8db", "#e5e5e5",
        ),
    },
}
