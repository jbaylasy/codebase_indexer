from __future__ import annotations

from pathlib import Path

import yaml
from tree_sitter import Language, Parser

from code_index.parsers.base import ASTNode, LanguageParser
from code_index.parsers.cpp_parser import CppParser
from code_index.parsers.go_parser import GoParser
from code_index.parsers.java_parser import JavaParser
from code_index.parsers.javascript_parser import JavaScriptParser
from code_index.parsers.python_parser import PythonParser
from code_index.parsers.rust_parser import RustParser
from code_index.parsers.typescript_parser import TypeScriptParser


class TreeSitterParser:
    def __init__(self):
        self._parsers: dict[str, LanguageParser] = {}
        self._languages: dict[str, Language] = {}
        self._ts_parsers: dict[str, Parser] = {}
        self._extension_map: dict[str, str] | None = None
        self._register_parsers()

    def _register_parsers(self):
        for cls in (PythonParser, JavaScriptParser, TypeScriptParser, RustParser, GoParser, JavaParser, CppParser):
            instance = cls()
            self._parsers[instance.language_id] = instance

    def _load_extension_map(self) -> dict[str, str]:
        if self._extension_map is None:
            yaml_path = Path(__file__).parent / "languages.yaml"
            with open(yaml_path) as f:
                data = yaml.safe_load(f)
            self._extension_map = {}
            if data:
                for ext, lang in data.items():
                    self._extension_map[ext] = lang
        return self._extension_map

    def get_language_for_extension(self, ext: str) -> str | None:
        mapping = self._load_extension_map()
        if not ext.startswith("."):
            ext = "." + ext
        return mapping.get(ext)

    def _ensure_language_loaded(self, language_id: str) -> Language:
        if language_id not in self._languages:
            strategy = self._parsers[language_id]
            if language_id == "typescript":
                import tree_sitter_typescript as tsts
                lang = Language(tsts.language_typescript())
            else:
                module = __import__(strategy.tree_sitter_module)
                lang = Language(module.language())
            self._languages[language_id] = lang
        return self._languages[language_id]

    def parse(self, source_code: str, language: str) -> list[ASTNode]:
        if language not in self._parsers:
            return []

        strategy = self._parsers[language]
        lang = self._ensure_language_loaded(language)

        if language not in self._ts_parsers:
            self._ts_parsers[language] = Parser(lang)
        ts_parser = self._ts_parsers[language]

        source_bytes = source_code.encode("utf-8")
        tree = ts_parser.parse(source_bytes)
        return strategy.extract_nodes(tree.root_node, source_bytes)
