import os
import tempfile
import pytest

from code_index.config_setup import (
    find_git_root,
    generate_config,
    CONFIG_FILENAME,
)
from code_index.config_loader import (
    find_config_file,
    load_config,
    get_codebases_from_config,
    get_extensions_from_config,
    get_exclude_from_config,
)


class TestFindGitRoot:
    def test_finds_git_root_from_cwd(self):
        root = find_git_root(os.getcwd())
        assert root is not None
        assert os.path.isdir(os.path.join(root, ".git"))

    def test_finds_git_root_from_subdirectory(self):
        subdir = os.path.join(os.getcwd(), "code_index")
        root = find_git_root(subdir)
        assert root == find_git_root(os.getcwd())

    def test_returns_none_for_no_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            assert find_git_root(tmp) is None


class TestGenerateConfig:
    def test_generates_valid_yaml(self):
        codebases = [
            {"name": "project_a", "root": "/tmp/a"},
            {"name": "project_b", "root": "/tmp/b"},
        ]
        text = generate_config(codebases)
        assert "project_a" in text
        assert "/tmp/a" in text
        assert "extensions:" in text
        assert "exclude:" in text

    def test_custom_extensions_and_exclude(self):
        text = generate_config(
            [{"name": "x", "root": "/x"}],
            extensions=[".py", ".rs"],
            exclude=["target", "build"],
        )
        assert ".rs" in text
        assert "target" in text


class TestConfigLoader:
    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        self._config_path = os.path.join(self._tmpdir, CONFIG_FILENAME)

    def _write_config(self, content):
        with open(self._config_path, "w") as f:
            f.write(content)

    def test_find_config_file(self):
        self._write_config("codebases: []\n")
        result = find_config_file(self._tmpdir)
        assert os.path.realpath(result) == os.path.realpath(self._config_path)

    def test_find_config_file_walks_up(self):
        subdir = os.path.join(self._tmpdir, "sub")
        os.makedirs(subdir)
        self._write_config("codebases: []\n")
        result = find_config_file(subdir)
        assert os.path.realpath(result) == os.path.realpath(self._config_path)

    def test_find_config_file_returns_none(self):
        assert find_config_file("/tmp") is None

    def test_load_config_parses_yaml(self):
        self._write_config("""
codebases:
  - name: myapp
    root: .
extensions:
  - .py
  - .rs
exclude:
  - target
""")
        parsed, path = load_config(self._tmpdir)
        assert os.path.realpath(path) == os.path.realpath(self._config_path)
        assert len(parsed["codebases"]) == 1
        assert parsed["codebases"][0]["name"] == "myapp"

    def test_load_config_returns_none_when_missing(self):
        parsed, path = load_config("/tmp")
        assert parsed is None
        assert path is None

    def test_get_codebases_resolves_relative_paths(self):
        self._write_config("""
codebases:
  - name: myapp
    root: .
""")
        codebases = get_codebases_from_config(self._tmpdir)
        assert len(codebases) == 1
        assert codebases[0]["name"] == "myapp"
        assert os.path.isabs(codebases[0]["root"])

    def test_get_codebases_skips_nonexistent_dirs(self):
        self._write_config("""
codebases:
  - name: missing
    root: /nonexistent/path/xyz
""")
        codebases = get_codebases_from_config(self._tmpdir)
        assert codebases == []

    def test_get_codebases_empty_when_no_config(self):
        assert get_codebases_from_config("/tmp") == []

    def test_get_extensions(self):
        self._write_config("extensions:\n  - .py\n  - .rs\n")
        exts = get_extensions_from_config(self._tmpdir)
        assert exts == [".py", ".rs"]

    def test_get_extensions_adds_dot_prefix(self):
        self._write_config("extensions:\n  - py\n  - rs\n")
        exts = get_extensions_from_config(self._tmpdir)
        assert exts == [".py", ".rs"]

    def test_get_exclude(self):
        self._write_config("exclude:\n  - node_modules\n  - .venv\n")
        excl = get_exclude_from_config(self._tmpdir)
        assert excl == ["node_modules", ".venv"]

    def teardown_method(self):
        import shutil
        if os.path.exists(self._tmpdir):
            shutil.rmtree(self._tmpdir)
