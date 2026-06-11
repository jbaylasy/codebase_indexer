import os
import pytest
from code_index.path_security import validate_root_dir, is_safe_path


def test_validate_root_dir_allows_cwd_subdirectory(tmp_path, monkeypatch):
    monkeypatch.setattr("code_index.config.ALLOWED_BASE_DIRS", [str(tmp_path)])
    sub = tmp_path / "myproject"
    sub.mkdir()
    result = validate_root_dir(str(sub))
    assert os.path.isabs(result)


def test_validate_root_dir_rejects_dotdot(tmp_path, monkeypatch):
    monkeypatch.setattr("code_index.config.ALLOWED_BASE_DIRS", [str(tmp_path)])
    with pytest.raises(ValueError, match="\\.\\."):
        validate_root_dir(str(tmp_path / ".." / "etc"))


def test_validate_root_dir_rejects_sensitive_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr("code_index.config.ALLOWED_BASE_DIRS", ["/etc"])
    with pytest.raises(ValueError, match="sensitive"):
        validate_root_dir("/etc")


def test_validate_root_dir_rejects_outside_allowed(tmp_path, monkeypatch):
    monkeypatch.setattr("code_index.config.ALLOWED_BASE_DIRS", [str(tmp_path)])
    with pytest.raises(ValueError, match="outside allowed"):
        validate_root_dir("/usr/local/bin")


def test_is_safe_path_within_root(tmp_path):
    sub = tmp_path / "src" / "main.py"
    sub.parent.mkdir(parents=True)
    sub.write_text("hello")
    assert is_safe_path(str(sub), str(tmp_path)) is True


def test_is_safe_path_outside_root(tmp_path):
    assert is_safe_path("/etc/passwd", str(tmp_path)) is False


def test_validate_root_dir_resolves_path(tmp_path, monkeypatch):
    monkeypatch.setattr("code_index.config.ALLOWED_BASE_DIRS", [str(tmp_path)])
    sub = tmp_path / "project"
    sub.mkdir()
    result = validate_root_dir(str(sub) + "/.")
    assert result == str(sub.resolve())


def test_validate_root_dir_rejects_ssh(monkeypatch):
    monkeypatch.setattr("code_index.config.ALLOWED_BASE_DIRS", [os.path.expanduser("~")])
    ssh_dir = os.path.expanduser("~/.ssh")
    if os.path.exists(ssh_dir):
        with pytest.raises(ValueError, match="sensitive"):
            validate_root_dir(ssh_dir)
