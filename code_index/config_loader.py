import os
from pathlib import Path

from code_index.config_setup import CONFIG_FILENAME, find_git_root


def find_config_file(start_dir=None):
    start = Path(start_dir or os.getcwd()).resolve()
    current = start
    while current != current.parent:
        if (current / CONFIG_FILENAME).is_file():
            return str(current / CONFIG_FILENAME)
        current = current.parent
    git_root = find_git_root(start_dir)
    if git_root and (Path(git_root) / CONFIG_FILENAME).is_file():
        return str(Path(git_root) / CONFIG_FILENAME)
    return None


def load_config(start_dir=None):
    config_path = find_config_file(start_dir)
    if config_path is None:
        return None, None

    with open(config_path, "r") as f:
        text = f.read()

    parsed = _load_yaml(text)
    return parsed, config_path


def _load_yaml(text):
    import yaml
    return yaml.safe_load(text) or {}


def get_codebases_from_config(start_dir=None):
    parsed, config_path = load_config(start_dir)
    if parsed is None:
        return []

    codebases_raw = parsed.get("codebases", [])
    if not codebases_raw:
        return []

    config_dir = os.path.dirname(config_path) if config_path else os.getcwd()
    result = []
    for cb in codebases_raw:
        if isinstance(cb, dict) and "name" in cb and "root" in cb:
            root = cb["root"]
            if not os.path.isabs(root):
                root = os.path.join(config_dir, root)
            root = os.path.abspath(root)
            if os.path.isdir(root):
                result.append({"name": cb["name"], "root": root})

    return result


def get_extensions_from_config(start_dir=None):
    parsed, _ = load_config(start_dir)
    if parsed is None:
        return None
    exts = parsed.get("extensions", None)
    if exts and isinstance(exts, list):
        return [e if e.startswith(".") else f".{e}" for e in exts]
    return None


def get_exclude_from_config(start_dir=None):
    parsed, _ = load_config(start_dir)
    if parsed is None:
        return None
    return parsed.get("exclude", None)
