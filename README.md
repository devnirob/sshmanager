# SSH Manager — a MobaXterm alternative for Linux

SSH Manager is a native Linux SSH client and SFTP file manager for people who want a focused **MobaXterm alternative on Linux** and a tabbed, **FileZilla-style SFTP client** in one desktop app. It combines saved servers, concurrent SSH terminals, and independent dual-pane SFTP sessions without Electron or a browser.

## Highlights

- Open multiple independent SSH terminal tabs at the same time.
- Open multiple independent SFTP tabs, each connected to its own server.
- Browse local and remote files side by side like FileZilla.
- Open or edit local files by double-clicking or using the right-click menu.
- Right-click local files to open/edit, upload, rename, trash, copy paths, create folders, or refresh.
- Right-click remote files to download, rename, delete, copy paths, create folders, or refresh.
- Select one item normally, use Ctrl/Shift for multiple items, and avoid stale selections across panes.
- Upload and download multiple files or complete directory trees away from the UI thread.
- Authenticate with passwords, private keys, or the SSH agent, including jump hosts.
- Save passwords in the Linux keyring through libsecret instead of a plaintext config file.
- Verify a new SFTP server's SHA-256 host-key fingerprint before trusting it.
- Use VS Code Dark, Light, or System colors in the app and terminal.

## Offline Debian/Ubuntu installation

Download `ssh-manager_2.0.1_amd64.deb` and its checksum from the [GitHub Releases page](https://github.com/devnirob/sshmanager/releases), then run:

```bash
sha256sum -c ssh-manager_2.0.1_amd64.deb.sha256
sudo apt install ./ssh-manager_2.0.1_amd64.deb
```

Version 2.0's `.deb` is intentionally much larger than the old 17–18 KB package. The old package held only the application source and asked APT to download GTK, VTE, Paramiko, libsecret, OpenSSH, and `sshpass`. The new architecture-specific package includes a private Python/GTK/VTE/Paramiko/OpenSSH runtime, so installation does not need the internet or those extra packages.

The offline package targets 64-bit (`amd64`) Debian/Ubuntu desktops with glibc 2.39 or newer (for example Debian 13 or Ubuntu 24.04). It does not bundle the Linux kernel, graphics stack, desktop session, or glibc. Build on the oldest distribution you intend to support when redistributing a locally built package.

After installation, launch **SSH Manager** from the application menu or run:

```bash
sshmanager
```

## Getting started

1. Create or select a server in the Server Library.
2. Enter its hostname, username, port, and authentication details.
3. Select **Save Server**.
4. Select **Open SSH** or **Browse Files**. Each click creates a separate connection tab.
5. Use **+ New SSH Tab** or **+ New SFTP Tab** after selecting another server to keep several sessions open together.

## SFTP file management

The left pane is the local computer and the right pane is the remote server. A normal click replaces the selection; Ctrl-click toggles items; Shift-click selects a range. Selecting the opposite pane clears the old pane's selection.

Double-click a local folder to enter it, or double-click a local file to open it in the desktop's default editor/application. Remote folders open on double-click; remote files download to the current local folder. Downloads ask before replacing or merging existing local items. Right-click either pane for the complete action menu. Local delete operations go to the desktop Trash; remote deletes are permanent and require confirmation.

## Security

On a first SFTP connection, compare the displayed SHA-256 fingerprint with a value obtained from the server administrator through a separate trusted channel. SSH host-key changes and SFTP host-key changes are rejected.

Application data is stored under:

```text
~/.config/sshmanager/
├── profiles.json
├── settings.json
└── known_hosts
```

These files and directories use user-only permissions. Passwords are not stored there; saved passwords go to the desktop keyring. See [SECURITY.md](SECURITY.md) for reporting guidance and [SECURITY_AUDIT.md](SECURITY_AUDIT.md) for the version 2.0 review and resolved findings.

## Terminal shortcuts

| Action | Shortcut |
|---|---|
| Copy selected text | `Ctrl+Shift+C` |
| Paste clipboard text | `Ctrl+Shift+V` |

Copy, Paste, Clear, Connect, Disconnect, and Open Separate Terminal are also available from each SSH tab.

## Build and test

Run the test suite:

```bash
./test.sh
```

Build the offline `.deb` from an amd64 Debian/Ubuntu development machine where the runtime packages are installed:

```bash
./build-deb.sh
```

The builder collects the private runtime, checks it without using the development Python packages, creates the package in `dist/`, and writes a SHA-256 checksum beside it.

For a lightweight source checkout install (which uses system dependencies), run `./install.sh`.

## Project status and license

Changes are recorded in [CHANGELOG.md](CHANGELOG.md). A source license has not been selected yet; until one is added, the project remains copyright-protected. Copyright notices for libraries redistributed in the offline package are included under `/usr/share/doc/ssh-manager/third-party/`.
