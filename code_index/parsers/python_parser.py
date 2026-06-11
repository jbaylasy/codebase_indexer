from __future__ import annotations

from code_index.parsers.base import ASTNode, LanguageParser


class PythonParser(LanguageParser):
    @property
    def language_id(self) -> str:
        return "python"

    @property
    def tree_sitter_module(self) -> str:
        return "tree_sitter_python"

    def extract_nodes(self, root_node, source_bytes: bytes) -> list[ASTNode]:
        results: list[ASTNode] = []
        self._walk(root_node, source_bytes, results, parent_name=None)
        return results

    def _walk(self, node, source_bytes: bytes, results: list[ASTNode], parent_name: str | None):
        if node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            name = self.get_node_text(name_node, source_bytes) if name_node else "<anonymous>"
            start = node.start_point.row + 1
            end = node.end_point.row + 1
            if end - start + 1 >= 3:
                content = self.get_node_text(node, source_bytes)
                docstring = self._extract_docstring(node, source_bytes)
                results.append(ASTNode(
                    node_type="class", name=name, start_line=start, end_line=end,
                    content=content, parent_name=parent_name, docstring=docstring,
                ))
            for child in node.children:
                self._walk(child, source_bytes, results, parent_name=name)
            return

        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            name = self.get_node_text(name_node, source_bytes) if name_node else "<anonymous>"
            start = node.start_point.row + 1
            end = node.end_point.row + 1
            if end - start + 1 >= 3:
                content = self.get_node_text(node, source_bytes)
                docstring = self._extract_docstring(node, source_bytes)
                node_type = "method" if parent_name is not None else "function"
                results.append(ASTNode(
                    node_type=node_type, name=name, start_line=start, end_line=end,
                    content=content, parent_name=parent_name, docstring=docstring,
                ))
            return

        for child in node.children:
            self._walk(child, source_bytes, results, parent_name=parent_name)

    def _extract_docstring(self, node, source_bytes: bytes) -> str | None:
        body = node.child_by_field_name("body")
        if body is None:
            return None
        for child in body.children:
            if child.type == "expression_statement":
                for sub in child.children:
                    if sub.type == "string":
                        text = self.get_node_text(sub, source_bytes)
                        if text.startswith(('"""', "'''")):
                            text = text[3:]
                            if text.endswith(('"""', "'''")):
                                text = text[:-3]
                        elif text.startswith(('"', "'")):
                            text = text[1:]
                            if text.endswith(('"', "'")):
                                text = text[:-1]
                        return text.strip()
                break
        return None
