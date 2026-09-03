from __future__ import annotations

import os
import shutil

from .models import ConnectionProfile


def ssh_command(
    profile: ConnectionProfile,
    password: str = "",
    password_fd: int | None = None,
) -> tuple[list[str], list[str]]:
    command = [
        "ssh",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ServerAliveInterval=30",
        "-o", "ServerAliveCountMax=3",
        "-o", "ForwardAgent=no",
        "-o", "ForwardX11=no",
        "-o", "ClearAllForwardings=yes",
        "-o", "HostKeyAlgorithms=-ssh-rsa",
        "-o", "PubkeyAcceptedAlgorithms=-ssh-rsa",
        "-p", str(profile.port),
    ]
    if profile.key_path:
        command.extend(["-i", os.path.expanduser(profile.key_path)])
    if profile.jump_host:
        command.extend(["-J", profile.jump_host])
    command.append(profile.target)

    env = [f"{key}={value}" for key, value in os.environ.items()]
    if password and password_fd is not None and shutil.which("sshpass"):
        command = ["sshpass", "-d", str(password_fd), *command]
    return command, env


def missing_dependencies() -> list[str]:
    missing: list[str] = []
    if not shutil.which("ssh"):
        missing.append("openssh-client")
    if not shutil.which("sshpass"):
        missing.append("sshpass")
    try:
        import paramiko  # noqa: F401
    except ImportError:
        missing.append("python3-paramiko")
    try:
        import gi
        gi.require_version("Vte", "2.91")
        from gi.repository import Vte  # noqa: F401
    except (ImportError, ValueError):
        missing.append("gir1.2-vte-2.91")
    return missing
