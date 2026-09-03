# Security audit — version 2.0.0

Audit date: 2026-09-03

## Scope

The review covered profile/settings persistence, secret storage, SSH command construction and process launch, SSH/SFTP host-key handling, local/remote path operations, destructive UI actions, concurrent session isolation, and the offline Debian package.

## Findings addressed

| Severity | Finding | Resolution |
|---|---|---|
| High | A server-controlled SFTP filename could escape the selected local download directory. | Every remote leaf name and resolved local destination is constrained to the selected directory. |
| High | A download could follow an existing local symbolic link and overwrite a file elsewhere. | Existing symlink destinations are rejected. |
| Medium | Paramiko silently accepted every first-seen SFTP host key. | First use now requires explicit approval of the key algorithm and SHA-256 fingerprint; changed keys are rejected. |
| Medium | Saved SSH passwords were inherited through the process environment. | Passwords are passed to `sshpass` through an anonymous file descriptor and are absent from argv/environment. |
| Medium | Connection fields accepted option-like and control-character values. | Hosts, users, jump hosts, ports, and paths are validated before use. Commands continue to use argument arrays without a shell. |
| Medium | Generated SSH sessions could inherit forwarding behavior from user configuration. | Agent, X11, local, remote, and dynamic forwarding are explicitly disabled. Legacy SHA-1 `ssh-rsa` is disabled in both SSH transports. |
| Medium | Downloads replaced existing local files without warning. | Existing top-level conflicts require a replace/merge confirmation; service-level downloads default to no overwrite. |
| Low | A malformed profiles file was replaced by a new empty library during startup. | The original file is preserved and a recoverable in-memory profile is opened with a visible warning. |
| Low | Existing config files could retain permissive modes. | App directories are repaired to `0700`; profiles, settings, and known-host files are repaired to `0600`. |
| Low | Closing a tab could leave descendants of its terminal process running. | Disconnect sends `SIGHUP` to the isolated child process group when available. |

## Dependency review

The bundled versions were checked against the Debian Security Tracker on the audit date:

- OpenSSH `1:10.0p1-7+deb13u4` has Debian-tracked minor/no-DSA issues involving concurrent remote forwarding and agent forwarding. Generated sessions explicitly disable those features.
- Paramiko `3.5.1-3` has a Debian-ignored SHA-1 compatibility issue. The application disables `ssh-rsa` for host keys and public-key signatures.
- python-cryptography `43.0.0-3+deb13u1` has minor/no-DSA X.509 name-constraint issues. SSH Manager does not use its X.509 verifier.

References:

- <https://security-tracker.debian.org/tracker/source-package/openssh>
- <https://security-tracker.debian.org/tracker/source-package/paramiko>
- <https://security-tracker.debian.org/tracker/source-package/python-cryptography>

## Residual considerations

- An offline bundle does not receive distribution library updates automatically. Rebuild and republish it after relevant Debian security updates.
- OpenSSH uses trust-on-first-use (`StrictHostKeyChecking=accept-new`) and rejects changed keys; SFTP provides an additional first-use fingerprint confirmation dialog.
- Remote deletion is necessarily permanent. The UI requires confirmation, while local deletion uses Trash.
- SSH keys protected by a passphrase or a local agent remain preferable to saved passwords.
