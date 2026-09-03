# Changelog

## 2.0.0 — 2026-09-03

- Add independent, closable tabs for concurrent SSH terminals and SFTP sessions.
- Add local file opening/editing and double-click behavior in the SFTP browser.
- Add local and remote right-click context menus with file-manager actions.
- Normalize single, multiple, and cross-pane selection behavior.
- Require explicit confirmation of new SFTP host-key fingerprints.
- Prevent server-controlled download path traversal and symbolic-link overwrites.
- Validate SSH connection fields before constructing commands.
- Keep an intentionally unsaved password available to the current session without persisting it.
- Replace the tiny dependency-only package with a private offline runtime bundle.
- Add AppStream metadata, search-focused desktop metadata, security guidance, and expanded documentation.
