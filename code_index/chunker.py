import os
import re
from concurrent.futures import ProcessPoolExecutor, as_completed
import signal

from code_index.parsers import TreeSitterParser
from code_index.parsers.base import ASTNode
from code_index.config import CHUNK_MAX_TOKENS, CHUNK_MIN_TOKENS, CHARS_PER_TOKEN

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024
CHUNK_TIMEOUT_SECONDS = 30

_ts_parser = None


def _get_ts_parser():
    global _ts_parser
    if _ts_parser is None:
        _ts_parser = TreeSitterParser()
    return _ts_parser


class _TimeoutError(Exception):
    pass


def _timeout_handler(signum, frame):
    raise _TimeoutError("Chunking timed out")


def _estimate_tokens(text):
    return len(text) // CHARS_PER_TOKEN


def _enrich_chunk_text(text, file_path, chunk_type, chunk_name, class_name=None, part_info=None):
    if class_name:
        context = f"File: {file_path} | class: {class_name}, {chunk_type}: {chunk_name}"
    else:
        context = f"File: {file_path} | {chunk_type}: {chunk_name}"
    if part_info:
        context += f" [{part_info}]"
    return f"{context}\n{text}"


def _extract_signature(content):
    lines = content.split('\n')
    for i, line in enumerate(lines):
        stripped = line.rstrip()
        if stripped.endswith((':', '{')):
            return '\n'.join(lines[:i + 1])
    return lines[0] if lines else content


def _split_oversized_node(node, max_chars):
    if len(node.content) <= max_chars:
        return [node]

    signature = _extract_signature(node.content)
    sig_line_count = signature.count('\n') + 1
    all_lines = node.content.split('\n')
    body_lines = all_lines[sig_line_count:]

    if not body_lines:
        return [node]

    sections = []
    current = []
    for line in body_lines:
        if line.strip() == '' and current:
            sections.append(current)
            current = []
        else:
            current.append(line)
    if current:
        sections.append(current)

    if len(sections) <= 1:
        sections = []
        current = []
        for line in body_lines:
            if current and len('\n'.join(current)) + len(signature) + len(line) > max_chars:
                sections.append(current)
                current = []
            current.append(line)
        if current:
            sections.append(current)

    if not sections:
        return [node]

    sub_chunks = []
    line_offset = 0
    for i, section in enumerate(sections):
        sub_content = signature + '\n' + '\n'.join(section)
        sub = ASTNode(
            node_type=node.node_type,
            name=node.name,
            start_line=node.start_line + sig_line_count + line_offset,
            end_line=node.start_line + sig_line_count + line_offset + len(section),
            content=sub_content,
            parent_name=node.parent_name,
            docstring=node.docstring if i == 0 else None,
        )
        sub_chunks.append(sub)
        line_offset += len(section)

    return sub_chunks if sub_chunks else [node]


def _ast_nodes_to_chunks(nodes, file_path, source_code):
    max_chars = CHUNK_MAX_TOKENS * CHARS_PER_TOKEN

    expanded = []
    for node in nodes:
        splits = _split_oversized_node(node, max_chars)
        for i, s in enumerate(splits):
            is_split = len(splits) > 1
            part_info = f"part {i + 1}/{len(splits)}" if is_split else None
            expanded.append((s, part_info))

    chunks = []
    for node, part_info in expanded:
        if _estimate_tokens(node.content) < CHUNK_MIN_TOKENS:
            continue
        chunk_text = node.content
        if node.docstring:
            chunk_text = f'"""\n{node.docstring}\n"""\n\n{chunk_text}'
        enriched = _enrich_chunk_text(
            chunk_text, file_path, node.node_type, node.name,
            node.parent_name, part_info
        )
        chunks.append({
            "text": enriched,
            "metadata": {
                "file": file_path,
                "start_line": node.start_line,
                "type": node.node_type,
                "name": node.name,
            },
        })

    return chunks


def _fallback_chunk(source_code, file_path):
    enriched = _enrich_chunk_text(source_code, file_path, "file", os.path.basename(file_path))
    return [{
        "text": enriched,
        "metadata": {
            "file": file_path,
            "start_line": 1,
            "type": "file",
            "name": os.path.basename(file_path),
        },
    }]


def split_with_treesitter(source_code, file_path):
    ext = os.path.splitext(file_path)[1].lower()
    parser = _get_ts_parser()
    language = parser.get_language_for_extension(ext)

    if language is None:
        return _fallback_chunk(source_code, file_path)

    try:
        nodes = parser.parse(source_code, language)
    except Exception:
        return _fallback_chunk(source_code, file_path)

    if not nodes:
        return _fallback_chunk(source_code, file_path)

    chunks = _ast_nodes_to_chunks(nodes, file_path, source_code)
    if not chunks:
        return _fallback_chunk(source_code, file_path)
    return chunks


def split_python_code(source_code, file_path, min_lines=3):
    return split_with_treesitter(source_code, file_path)


def split_js_ts_code(source_code, file_path):
    return split_with_treesitter(source_code, file_path)


def _chunk_file(file_path):
    try:
        file_size = os.path.getsize(file_path)
    except OSError:
        return []

    if file_size > MAX_FILE_SIZE_BYTES:
        return []

    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except (OSError, UnicodeDecodeError):
        return []

    old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(CHUNK_TIMEOUT_SECONDS)
    try:
        result = split_with_treesitter(content, file_path)
    except _TimeoutError:
        return []
    except RecursionError:
        return []
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)

    return result


def _collect_file_paths(root_dir):
    allowed_extensions = [
        ".py", ".js", ".jsx", ".ts", ".tsx", ".rs", ".go", ".java",
        ".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hxx",
        ".md", ".txt", ".json", ".sql",
    ]
    file_paths = []
    for root, dirs, files in os.walk(root_dir):
        for d in dirs[:]:
            if d.startswith("."):
                dirs.remove(d)
        for file in files:
            if any(file.endswith(ext) for ext in allowed_extensions):
                file_paths.append(os.path.join(root, file))
    return file_paths


def get_file_paths(root_dir, max_workers=None):
    from code_index.secret_scanner import redact_chunk

    file_paths = _collect_file_paths(root_dir)

    if not file_paths:
        return []

    workers = max_workers or min(os.cpu_count() or 4, 8)

    if len(file_paths) < 10:
        all_chunks = []
        for fp in file_paths:
            chunks = _chunk_file(fp)
            all_chunks.extend(redact_chunk(c) for c in chunks)
        return all_chunks

    all_chunks = []
    try:
        multiprocessing.set_start_method("spawn", force=True)
    except RuntimeError:
        pass
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_chunk_file, fp): fp for fp in file_paths}
        for future in as_completed(futures):
            try:
                chunks = future.result()
                all_chunks.extend(redact_chunk(c) for c in chunks)
            except Exception:
                pass

    return all_chunks


def sanitize_pattern(pattern):
    if not pattern or not isinstance(pattern, str):
        return ""
    max_length = 500
    if len(pattern) > max_length:
        pattern = pattern[:max_length]
    try:
        compiled = re.compile(pattern)
        if len(compiled.pattern) > max_length:
            return ""
        return pattern
    except re.error:
        return ""
