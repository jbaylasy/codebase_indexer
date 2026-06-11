from __future__ import annotations

from code_index.parsers.base import ASTNode, LanguageParser


class GoParser(LanguageParser):
    @property
    def language_id(self) -> str:
        return "go"

    @property
    def tree_sitter_module(self) -> str:
        return "tree_sitter_go"

    def extract_nodes(self, root_node, source_bytes: bytes) -> list[ASTNode]:
        results: list[ASTNode] = []
        self._walk(root_node, source_bytes, results)
        return results

    def _walk(self, node, source_bytes: bytes, results: list[ASTNode]):
        if node.type == "function_declaration":
            name_node = node.child_by_field_name("name")
            name = self.get_node_text(name_node, source_bytes) if name_node else "<anonymous>"
            start = node.start_point.row + 1
            end = node.end_point.row + 1
            if end - start + 1 >= 3:
                content = self.get_node_text(node, source_bytes)
                results.append(ASTNode(
                    node_type="function", name=name, start_line=start, end_line=end,
                    content=content,
                ))
            return

        if node.type == "method_declaration":
            name_node = node.child_by_field_name("name")
            name = self.get_node_text(name_node, source_bytes) if name_node else "<anonymous>"
            receiver_node = node.child_by_field_name("receiver")
            parent_name = None
            if receiver_node:
                parent_name = self._extract_receiver_type(receiver_node, source_bytes)
            start = node.start_point.row + 1
            end = node.end_point.row + 1
            if end - start + 1 >= 3:
                content = self.get_node_text(node, source_bytes)
                results.append(ASTNode(
                    node_type="method", name=name, start_line=start, end_line=end,
                    content=content, parent_name=parent_name,
                ))
            return

        if node.type == "type_declaration":
            for child in node.children:
                if child.type == "type_spec":
                    name_node = child.child_by_field_name("name")
                    name = self.get_node_text(name_node, source_bytes) if name_node else "<anonymous>"
                    type_node = child.child_by_field_name("type")
                    node_type = "type"
                    if type_node and type_node.type == "struct_type":
                        node_type = "struct"
                    elif type_node and type_node.type == "interface_type":
                        node_type = "interface"
                    start = node.start_point.row + 1
                    end = node.end_point.row + 1
                    if end - start + 1 >= 3:
                        content = self.get_node_text(node, source_bytes)
                        results.append(ASTNode(
                            node_type=node_type, name=name, start_line=start, end_line=end,
                            content=content,
                        ))
            return

        for child in node.children:
            self._walk(child, source_bytes, results)

    def _extract_receiver_type(self, receiver_node, source_bytes: bytes) -> str | None:
        text = self.get_node_text(receiver_node, source_bytes)
        text = text.strip().strip("()")
        if not text:
            return None
        if "*" in text:
            parts = text.split("*")
            for p in reversed(parts):
                p = p.strip()
                if p:
                    return p
        tokens = text.split()
        if len(tokens) >= 2:
            return tokens[0].strip("*")
        return text.strip("*") or None
