from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ASTNode:
    node_type: str
    name: str
    start_line: int
    end_line: int
    content: str
    parent_name: str | None = None
    docstring: str | None = None


class LanguageParser(ABC):
    @property
    @abstractmethod
    def language_id(self) -> str: ...

    @property
    @abstractmethod
    def tree_sitter_module(self) -> str: ...

    @abstractmethod
    def extract_nodes(self, root_node, source_bytes: bytes) -> list[ASTNode]: ...

    @staticmethod
    def get_node_text(node, source_bytes: bytes) -> str:
        return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
