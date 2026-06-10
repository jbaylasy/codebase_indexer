import os
import ast
import re
from concurrent.futures import ProcessPoolExecutor, as_completed


JS_TS_EXTENSIONS = (".js", ".jsx", ".ts", ".tsx")

JS_TS_PATTERNS = [
    re.compile(r"(?:export\s+)?default\s+function\s+(\w+)\s*[<(]", re.MULTILINE),
    re.compile(r"(?:export\s+)?default\s+class\s+(\w+)\s*(?:extends\s+\w+\s*)?\{", re.MULTILINE),
    re.compile(r"(?:export\s+)?async\s+function\s+(\w+)\s*[<(]", re.MULTILINE),
    re.compile(r"(?:export\s+)?function\s+(\w+)\s*[<(]", re.MULTILINE),
    re.compile(r"(?:export\s+)?class\s+(\w+)\s*(?:extends\s+[\w.]+\s*)?(?:implements\s+[\w,\s]+\s*)?\{", re.MULTILINE),
    re.compile(r"(?:export\s+)?interface\s+(\w+)\s*(?:extends\s+[\w,\s]+\s*)?\{", re.MULTILINE),
    re.compile(r"(?:export\s+)?type\s+(\w+)\s*(?:<[^>]+>)?\s*=", re.MULTILINE),
    re.compile(r"(?:export\s+)?const\s+(\w+)\s*(?::\s*[^=]+)?\s*=\s*(?:\([^)]*\)|[^=])\s*=>", re.MULTILINE),
    re.compile(r"(?:export\s+)?const\s+(\w+)\s*=\s*function", re.MULTILINE),
    re.compile(r"(?:export\s+)?const\s+(\w+)\s*=\s*React\.forwardRef", re.MULTILINE),
    re.compile(r"(?:public|private|protected)?\s*(?:static\s+)?(?:async\s+)?(\w+)\s*\([^)]*\)\s*(?::\s*[^{]+)?\{", re.MULTILINE),
]


def _enrich_chunk_text(text, file_path, chunk_type, chunk_name, class_name=None):
    if class_name:
        context = f"File: {file_path} | class: {class_name}, {chunk_type}: {chunk_name}"
    else:
        context = f"File: {file_path} | {chunk_type}: {chunk_name}"
    return f"{context}\n{text}"


def split_python_code(source_code, file_path, min_lines=3):
    """Parse a Python file into individual function and class chunks using AST.

    Args:
        source_code: The raw Python source code as a string.
        file_path: The file path, used for metadata.
        min_lines: Minimum number of lines a chunk must have to be included.

    Returns:
        A list of dicts, each containing the code text and metadata (file, line, type, name).
    """
    chunks = []
    try:
        tree = ast.parse(source_code)
        lines = source_code.split('\n')

        parent_map = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parent_map[child] = parent

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                start_line = node.lineno - 1
                end_line = node.end_lineno
                chunk_text = "\n".join(lines[start_line:end_line])

                if len(chunk_text.strip().split('\n')) < min_lines:
                    continue

                docstring = ast.get_docstring(node) or ""

                chunk_text_with_context = chunk_text
                if docstring:
                    chunk_text_with_context = f'"""\n{docstring}\n"""\n\n{chunk_text}'

                chunk_type = "function" if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else "class"

                class_name = None
                if chunk_type == "function":
                    parent = parent_map.get(node)
                    if isinstance(parent, ast.ClassDef):
                        class_name = parent.name

                enriched_text = _enrich_chunk_text(
                    chunk_text_with_context, file_path, chunk_type, node.name, class_name
                )

                chunks.append({
                    "text": enriched_text,
                    "metadata": {
                        "file": file_path,
                        "start_line": start_line + 1,
                        "type": chunk_type,
                        "name": node.name,
                    }
                })
    except SyntaxError:
        pass
    return chunks


def split_js_ts_code(source_code, file_path):
    """Parse a JS/TS file into function and class chunks using regex patterns.

    Since AST parsing only works for Python, this uses regex to extract
    function declarations, class declarations, and named arrow functions
    from JavaScript and TypeScript source code.

    Args:
        source_code: The raw JS/TS source code as a string.
        file_path: The file path, used for metadata.

    Returns:
        A list of dicts, each containing the code text and metadata.
    """
    chunks = []
    lines = source_code.split('\n')
    seen_spans = []

    for pattern in JS_TS_PATTERNS:
        for match in pattern.finditer(source_code):
            name = match.group(1)
            if not name or not name[0].isalpha() and name[0] != '_':
                continue

            start_pos = match.start()
            start_line = source_code[:start_pos].count('\n')

            if start_line >= len(lines):
                continue

            end_line = _find_block_end(lines, start_line)

            span = (start_line, end_line)
            if any(s[0] <= start_line < s[1] for s in seen_spans):
                continue
            seen_spans.append(span)

            chunk_text = "\n".join(lines[start_line:end_line + 1])

            chunk_type = "class"
            match_text = match.group(0)
            if "function" in match_text or "=>" in match_text or "const" in match_text:
                chunk_type = "function"
            elif "interface" in match_text:
                chunk_type = "interface"
            elif "type " in match_text and "= " in match_text:
                chunk_type = "type"

            enriched_text = _enrich_chunk_text(chunk_text, file_path, chunk_type, name)

            chunks.append({
                "text": enriched_text,
                "metadata": {
                    "file": file_path,
                    "start_line": start_line + 1,
                    "type": chunk_type,
                    "name": name,
                }
            })

    if not chunks:
        enriched_text = _enrich_chunk_text(source_code, file_path, "file", os.path.basename(file_path))
        chunks.append({
            "text": enriched_text,
            "metadata": {
                "file": file_path,
                "start_line": 1,
                "type": "file",
                "name": os.path.basename(file_path),
            }
        })

    return chunks


def _find_block_end(lines, start_line):
    """Find the end line of a brace-delimited block starting at start_line.

    Args:
        lines: List of source code lines.
        start_line: The line index where the block starts.

    Returns:
        The line index of the block's closing brace, or the last line if unmatched.
    """
    depth = 0
    found_open = False
    for i in range(start_line, len(lines)):
        for ch in lines[i]:
            if ch == '{':
                depth += 1
                found_open = True
            elif ch == '}':
                depth -= 1
                if found_open and depth == 0:
                    return i
    return len(lines) - 1


def _chunk_file(file_path):
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    if file_path.endswith(".py"):
        return split_python_code(content, file_path)
    elif file_path.endswith(JS_TS_EXTENSIONS):
        return split_js_ts_code(content, file_path)
    else:
        enriched_text = _enrich_chunk_text(content, file_path, "file", os.path.basename(file_path))
        return [{
            "text": enriched_text,
            "metadata": {
                "file": file_path,
                "start_line": 1,
                "type": "file",
                "name": os.path.basename(file_path),
            }
        }]


def _collect_file_paths(root_dir):
    allowed_extensions = [".py", ".js", ".jsx", ".ts", ".tsx", ".md", ".txt", ".json", ".sql"]
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
    """Walk a directory tree, read allowed file types, and return a list of chunk dicts.

    Uses multiprocessing to parallelize file reading and chunking during initial indexing.
    Python files are split into function/class chunks via AST.
    JS/TS files are split into function/class chunks via regex.
    All other allowed files are stored as-is (whole file).

    Args:
        root_dir: The root directory to scan.
        max_workers: Max number of worker processes (default: os.cpu_count()).

    Returns:
        A list of dicts with 'text' and 'metadata' keys.
    """
    file_paths = _collect_file_paths(root_dir)

    if not file_paths:
        return []

    workers = max_workers or min(os.cpu_count() or 4, 8)

    if len(file_paths) < 10:
        all_chunks = []
        for fp in file_paths:
            all_chunks.extend(_chunk_file(fp))
        return all_chunks

    all_chunks = []
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_chunk_file, fp): fp for fp in file_paths}
        for future in as_completed(futures):
            try:
                all_chunks.extend(future.result())
            except Exception:
                pass

    return all_chunks
