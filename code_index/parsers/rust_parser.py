from __future__ import annotations

from code_index.parsers.base import ASTNode, LanguageParser


class RustParser(LanguageParser):
    @property
    def language_id(self) -> str:
        return "rust"

    @property
    def tree_sitter_module(self) -> str:
        return "tree_sitter_rust"

    def extract_nodes(self, root_node, source_bytes: bytes) -> list[ASTNode]:
        results: list[ASTNode] = []
        self._walk(root_node, source_bytes, results, parent_name=None)
        return results

    def _walk(self, node, source_bytes: bytes, results: list[ASTNode], parent_name: str | None):
        if node.type == "impl_item":
            type_node = node.child_by_field_name("type")
            impl_name = self.get_node_text(type_node, source_bytes) if type_node else None
            for child in node.children:
                if child.type == "function_item":
                    name_node = child.child_by_field_name("name")
                    name = self.get_node_text(name_node, source_bytes) if name_node else "<anonymous>"
                    start = child.start_point.row + 1
                    end = child.end_point.row + 1
                    if end - start + 1 >= 3:
                        content = self.get_node_text(child, source_bytes)
                        results.append(ASTNode(
                            node_type="method", name=name, start_line=start, end_line=end,
                            content=content, parent_name=impl_name,
                        ))
            return

        if node.type == "function_item":
            name_node = node.child_by_field_name("name")
            name = self.get_node_text(name_node, source_bytes) if name_node else "<anonymous>"
            start = node.start_point.row + 1
            end = node.end_point.row + 1
            if end - start + 1 >= 3:
                content = self.get_node_text(node, source_bytes)
                results.append(ASTNode(
                    node_type="function", name=name, start_line=start, end_line=end,
                    content=content, parent_name=parent_name,
                ))
            return

        if node.type == "struct_item":
            name_node = node.child_by_field_name("name")
            name = self.get_node_text(name_node, source_bytes) if name_node else "<anonymous>"
            start = node.start_point.row + 1
            end = node.end_point.row + 1
            if end - start + 1 >= 3:
                content = self.get_node_text(node, source_bytes)
                results.append(ASTNode(
                    node_type="struct", name=name, start_line=start, end_line=end,
                    content=content, parent_name=parent_name,
                ))
            return

        if node.type == "enum_item":
            name_node = node.child_by_field_name("name")
            name = self.get_node_text(name_node, source_bytes) if name_node else "<anonymous>"
            start = node.start_point.row + 1
            end = node.end_point.row + 1
            if end - start + 1 >= 3:
                content = self.get_node_text(node, source_bytes)
                results.append(ASTNode(
                    node_type="struct", name=name, start_line=start, end_line=end,
                    content=content, parent_name=parent_name,
                ))
            return

        if node.type == "trait_item":
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
            return

        for child in node.children:
            self._walk(child, source_bytes, results, parent_name=parent_name)
