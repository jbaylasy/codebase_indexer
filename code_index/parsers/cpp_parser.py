from __future__ import annotations

from code_index.parsers.base import ASTNode, LanguageParser


class CppParser(LanguageParser):
    @property
    def language_id(self) -> str:
        return "cpp"

    @property
    def tree_sitter_module(self) -> str:
        return "tree_sitter_cpp"

    def extract_nodes(self, root_node, source_bytes: bytes) -> list[ASTNode]:
        results: list[ASTNode] = []
        self._walk(root_node, source_bytes, results, parent_name=None)
        return results

    def _walk(self, node, source_bytes: bytes, results: list[ASTNode], parent_name: str | None):
        if node.type == "class_specifier":
            name = self._get_class_name(node, source_bytes)
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

        if node.type == "struct_specifier":
            name = self._get_class_name(node, source_bytes)
            start = node.start_point.row + 1
            end = node.end_point.row + 1
            if end - start + 1 >= 3:
                content = self.get_node_text(node, source_bytes)
                results.append(ASTNode(
                    node_type="struct", name=name, start_line=start, end_line=end,
                    content=content, parent_name=parent_name,
                ))
            for child in node.children:
                self._walk(child, source_bytes, results, parent_name=name)
            return

        if node.type == "function_definition":
            declarator = node.child_by_field_name("declarator")
            name = self._extract_function_name(declarator, source_bytes) if declarator else "<anonymous>"
            start = node.start_point.row + 1
            end = node.end_point.row + 1
            if end - start + 1 >= 3:
                content = self.get_node_text(node, source_bytes)
                results.append(ASTNode(
                    node_type="function", name=name, start_line=start, end_line=end,
                    content=content, parent_name=parent_name,
                ))
            return

        for child in node.children:
            self._walk(child, source_bytes, results, parent_name=parent_name)

    def _get_class_name(self, node, source_bytes: bytes) -> str:
        name_node = node.child_by_field_name("name")
        if name_node:
            return self.get_node_text(name_node, source_bytes)
        return "<anonymous>"

    def _extract_function_name(self, declarator, source_bytes: bytes) -> str:
        if declarator.type == "function_declarator":
            decl = declarator.child_by_field_name("declarator")
            if decl:
                return self._extract_function_name(decl, source_bytes)
            name_node = declarator.child_by_field_name("declarator")
            if name_node is None:
                for child in declarator.children:
                    if child.type == "identifier" or child.type == "field_identifier" or child.type == "qualified_identifier":
                        return self.get_node_text(child, source_bytes)
            return self.get_node_text(declarator, source_bytes).split("(")[0].strip()
        if declarator.type in ("identifier", "field_identifier", "qualified_identifier"):
            return self.get_node_text(declarator, source_bytes)
        for child in declarator.children:
            if child.type in ("identifier", "field_identifier", "qualified_identifier"):
                return self.get_node_text(child, source_bytes)
        return "<anonymous>"
