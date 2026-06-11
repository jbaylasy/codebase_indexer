from __future__ import annotations

from code_index.parsers.base import ASTNode, LanguageParser


class JavaParser(LanguageParser):
    @property
    def language_id(self) -> str:
        return "java"

    @property
    def tree_sitter_module(self) -> str:
        return "tree_sitter_java"

    def extract_nodes(self, root_node, source_bytes: bytes) -> list[ASTNode]:
        results: list[ASTNode] = []
        self._walk(root_node, source_bytes, results, parent_name=None)
        return results

    def _walk(self, node, source_bytes: bytes, results: list[ASTNode], parent_name: str | None):
        if node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            name = self.get_node_text(name_node, source_bytes) if name_node else "<anonymous>"
            start = node.start_point.row + 1
            end = node.end_point.row + 1
            if end - start + 1 >= 3:
                content = self.get_node_text(node, source_bytes)
                results.append(ASTNode(
                    node_type="class", name=name, start_line=start, end_line=end,
                    content=content, parent_name=parent_name,
                ))
            for child in node.children:
                self._walk(child, source_bytes, results, parent_name=name)
            return

        if node.type == "interface_declaration":
            name_node = node.child_by_field_name("name")
            name = self.get_node_text(name_node, source_bytes) if name_node else "<anonymous>"
            start = node.start_point.row + 1
            end = node.end_point.row + 1
            if end - start + 1 >= 3:
                content = self.get_node_text(node, source_bytes)
                results.append(ASTNode(
                    node_type="interface", name=name, start_line=start, end_line=end,
                    content=content, parent_name=parent_name,
                ))
            for child in node.children:
                self._walk(child, source_bytes, results, parent_name=name)
            return

        if node.type == "method_declaration":
            name_node = node.child_by_field_name("name")
            name = self.get_node_text(name_node, source_bytes) if name_node else "<anonymous>"
            start = node.start_point.row + 1
            end = node.end_point.row + 1
            if end - start + 1 >= 3:
                content = self.get_node_text(node, source_bytes)
                results.append(ASTNode(
                    node_type="method", name=name, start_line=start, end_line=end,
                    content=content, parent_name=parent_name,
                ))
            return

        if node.type == "constructor_declaration":
            name_node = node.child_by_field_name("name")
            name = self.get_node_text(name_node, source_bytes) if name_node else "<init>"
            start = node.start_point.row + 1
            end = node.end_point.row + 1
            if end - start + 1 >= 3:
                content = self.get_node_text(node, source_bytes)
                results.append(ASTNode(
                    node_type="method", name=name, start_line=start, end_line=end,
                    content=content, parent_name=parent_name,
                ))
            return

        for child in node.children:
            self._walk(child, source_bytes, results, parent_name=parent_name)
