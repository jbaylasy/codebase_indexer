import os
from pathlib import Path

from code_index import config as _config

SENSITIVE_DIR_PREFIXES = [
    "/etc",
    "/root",
    "/var/log",
    "/var/run",
    os.path.expanduser("~/.ssh"),
    os.path.expanduser("~/.gnupg"),
    os.path.expanduser("~/.aws"),
    os.path.expanduser("~/.kube"),
    "/proc",
    "/sys",
    "/dev",
    "/boot",
    "/sbin",
    "/usr/sbin",
]


def validate_root_dir(path):
    resolved = Path(path).resolve()

    if ".." in Path(path).parts:
        raise ValueError(f"Path contains '..' component: {path}")

    if resolved.is_symlink():
        target = resolved.resolve()
        target_str = str(target)
    else:
        target_str = str(resolved)

    target_str = target_str.rstrip(os.sep) + os.sep

    for prefix in SENSITIVE_DIR_PREFIXES:
        prefix_resolved = str(Path(prefix).resolve()).rstrip(os.sep) + os.sep
        if target_str.startswith(prefix_resolved) or str(resolved).startswith(prefix_resolved.rstrip(os.sep)):
            raise ValueError(f"Path points to a sensitive directory: {path}")

    allowed_dirs = _config.ALLOWED_BASE_DIRS
    allowed_found = False
    for base in allowed_dirs:
        base_resolved = str(Path(base).resolve()).rstrip(os.sep) + os.sep
        if str(resolved).startswith(base_resolved.rstrip(os.sep)):
            allowed_found = True
            break
    if not allowed_found:
        raise ValueError(
            f"Path '{path}' is outside allowed directories: {allowed_dirs}"
        )

    return str(resolved)


def is_safe_path(file_path, root_dir):
    try:
        resolved = Path(file_path).resolve()
        root_resolved = Path(root_dir).resolve()
        resolved.relative_to(root_resolved)
        if resolved.is_symlink():
            target = resolved.resolve()
            target.relative_to(root_resolved)
        return True
    except ValueError:
        return False
