# SSH Manager

SSH Manager is a small desktop application for working with SSH servers on Debian and Ubuntu. It keeps saved connections, an SSH terminal, and an SFTP file browser in the same window.

I built it for the routine jobs where opening several terminal and file-transfer applications feels unnecessary. It uses OpenSSH and VTE for terminal sessions and Paramiko for SFTP.

## What it does

- Saves connection details such as host, port, username, private key, jump host, and remote path
- Opens SSH sessions in an embedded terminal
- Copies and pastes with `Ctrl+Shift+C` and `Ctrl+Shift+V`
- Works with passwords, private keys, and the SSH agent
- Stores saved passwords in the Linux keyring
- Browses local and remote files side by side
- Uploads and downloads multiple files or complete folders
- Creates, renames, and removes remote files and folders
- Keeps file transfers off the main UI thread
- Includes VS Code Dark, Light, and System themes
- Uses the correct application identity and icon on Wayland and X11

## Installation

Download the current `.deb` from the [Releases page](https://github.com/devnirob/sshmanager/releases) and install it with `apt`:

```bash
sudo apt install ./ssh-manager_1.1.0_all.deb
```

Using `apt` is recommended because it also installs the GTK, VTE, OpenSSH, Paramiko, and keyring packages required by the application.

Once installed, open **SSH Manager** from the application menu or run:

```bash
sshmanager
```

## Supported systems

The package is built to work on:

- Debian 11, 12, and 13
- Ubuntu 20.04 LTS and newer releases
- Debian or Ubuntu derivatives that provide the dependency packages listed in the `.deb`

The package is architecture-independent because the application itself is Python. Its native GTK and SSH components come from the distribution's package manager. This is also why the download is small; it does not contain duplicate copies of libraries already maintained by the operating system.

On a derivative that uses different package names, the application may work but the `.deb` might not resolve its dependencies automatically.

## Getting started

1. Create a server entry or select the default one.
2. Fill in the hostname, username, port, and authentication details.
3. Click **Save Server**.
4. Choose **Open SSH** for a terminal or **Browse Files** for SFTP.

Appearance settings are available from the button in the title bar. VS Code Dark is used by default.

## Terminal shortcuts

| Action | Shortcut |
|---|---|
| Copy selected text | `Ctrl+Shift+C` |
| Paste clipboard text | `Ctrl+Shift+V` |

Copy, Paste, Clear, Connect, and Disconnect are also available from the terminal toolbar.

## Where data is stored

Connection profiles are saved in:

```text
~/.config/sshmanager/profiles.json
```

Theme settings and accepted SFTP host keys are stored in the same directory. Profile and settings files are created with user-only permissions.

Passwords are not written to the profile file. When password saving is enabled, they are stored through libsecret in the desktop keyring. SSH keys and an SSH agent are still the better choice for security-sensitive servers.

## Notes

- Install the package with `apt`, not `dpkg -i`, if you want dependencies resolved automatically.
- A changed SFTP host key is rejected.
- The separate-terminal option uses the system's `x-terminal-emulator`.

## License

A license has not been selected yet. Until one is added, the source and application remain copyright-protected.
