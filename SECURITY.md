# Security policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately through GitHub's **Security → Report a vulnerability** flow instead of opening a public issue. Include the affected version, reproduction steps, and impact when possible.

## Security design

- Saved passwords are stored by the desktop keyring through libsecret, never in `profiles.json`.
- Profile and host-key files use user-only permissions.
- SFTP shows the server key algorithm and SHA-256 fingerprint before trusting a host for the first time. A changed known key is rejected.
- Downloads reject traversal components and existing symbolic-link destinations supplied through an untrusted server listing.
- SSH commands are passed as argument arrays, not through a command shell, and connection fields that could be treated as options are rejected.
- Saved SSH passwords are handed to `sshpass` through an anonymous file descriptor, not command arguments or process environment variables.
- Generated connections disable agent, X11, and port forwarding and exclude the legacy SHA-1 `ssh-rsa` algorithm.
- Local deletion uses the desktop Trash. Remote deletion is permanent and always asks for confirmation.

Users should prefer SSH keys protected by a passphrase or an SSH agent, verify first-use fingerprints through a separate trusted channel, and keep the operating system updated.
