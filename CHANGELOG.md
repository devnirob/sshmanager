# Changelog

## 2.1.1 — 2026-09-10

- Fix the New SSH Tab action so it saves and validates the current server form
  before opening a connection, matching the Open SSH action.
- Apply the same current-form handling to New SFTP Tab.

## 2.1.0 — 2026-09-04

- Add a persistent SFTP transfer panel with the active filename, per-file bytes,
  overall percentage, completed file count, remaining bytes, speed, and ETA.
- Speed up batches of small files with up to four SFTP channels per connection.
- Remove Paramiko's redundant post-upload `stat` round trip while retaining SFTP
  write acknowledgements, and enable bounded download prefetching.
- Throttle progress rendering so large batches do not flood the GTK event queue.
- Make the main Refresh Both action reload both current local and remote folders.

## 2.0.1 — 2026-09-04

- Fix password SSH sessions ending with encoded status 1280 because the secure
  password pipe was not mapped to the descriptor read by `sshpass`.
- Show the decoded SSH exit code and a clear saved-password message when
  authentication is rejected.

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
