# Semantic Code Search

Local-first semantic code search engine with MCP server, live file watching, and AST-aware chunking via tree-sitter.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Semantic Code Search Architecture                 │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐    ┌────────────────┐    ┌──────────┐             │
│  │ Source Files  │───>│ Tree-sitter    │───>│ Embedder │             │
│  │ (8+ langs)   │    │ Chunker        │    │ (sbert)  │             │
│  └──────────────┘    └────────────────┘    └────┬─────┘             │
│                                                  │                   │
│                                            ┌─────▼─────┐            │
│                                            │  LanceDB   │            │
│                                            │ (vectors + │            │
│                                            │  FTS idx)  │            │
│                                            └─────┬─────┘            │
│                                                  │                   │
│                         ┌────────────────────────┼──────────┐        │
│                         │                        │          │        │
│                   ┌─────▼──────┐   ┌────────────▼───┐  ┌──▼───────┐ │
│                   │ MCP Server │   │   Watcher      │  │   CLI    │ │
│                   │ (FastMCP)  │   │  (Watchdog)    │  │ (click)  │ │
│                   │  3 tools   │   │  debounced     │  │          │ │
│                   └─────┬──────┘   └────────────────┘  └──────────┘ │
│                         │                                             │
│                   ┌─────▼──────┐                                     │
│                   │  AI Agents │                                     │
│                   │ Claude /   │                                     │
│                   │ Cursor /   │                                     │
│                   │ opencode   │                                     │
│                   └────────────┘                                     │
└──────────────────────────────────────────────────────────────────────┘
```

## Key Features

- **Tree-sitter AST-aware chunking** for Python, JS/TS, Rust, Go, Java, C/C++
- **Hybrid search** -- vector similarity + full-text search merged with Reciprocal Rank Fusion (RRF)
- **Merkle tree incremental indexing** -- only re-indexes changed files via MD5 hash comparison
- **Live file watching** with debounced (2s) per-file updates
- **MCP server** for AI agent integration (Claude Code, Cursor, opencode)
- **Secret scanning and redaction** -- AWS keys, JWTs, private keys, database URLs, high-entropy strings
- **LanceDB encrypted at rest** via Fernet symmetric encryption with PBKDF2 key derivation
- **One-command setup** with `.codeindex.yml` config auto-detection

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11+ |
| AST Parsing | Tree-sitter (8+ languages) |
| Vector Store | LanceDB (local, persistent) |
| Embeddings | sentence-transformers (`all-MiniLM-L6-v2` or `nomic-embed-code`) |
| MCP Server | FastMCP (`mcp[cli]`) |
| File Watching | Watchdog |
| Config | YAML (`.codeindex.yml`) |
| Encryption | `cryptography` (Fernet + PBKDF2) |
| Testing | pytest |

## Quick Start

```bash
uv sync
uv run code-index           # interactive setup on first run, then MCP server
uv run code-index index     # one-shot index
uv run code-index search --query "auth logic" --codebase my_project
uv run code-index setup     # re-run config setup
```

## Project Structure

```
code_index/                         Core library
  __init__.py                       Re-exports public API
  cli.py                            CLI entry point (click) -- serve, index, search, setup
  config.py                         Environment variable configuration (dotenv)
  config_loader.py                  YAML config loader -- walks up to git root
  config_setup.py                   Interactive first-time setup wizard
  chunker.py                        Tree-sitter chunking with process pool
  embedder.py                       sentence-transformers with LRU cache + warm-up
  database.py                       LanceDB client, indexing, Merkle tree change detection
  search.py                         Hybrid search (vector + FTS) with Reciprocal Rank Fusion
  watcher.py                        Background file watcher (Watchdog) -- debounced updates
  secret_scanner.py                 Secret detection and redaction
  encryption.py                     DB encryption at rest (Fernet + PBKDF2)
  path_security.py                  Path validation and traversal prevention
  parser.py                         Parses questions.md into per-codebase question lists
  exporter.py                       Writes search results to per-codebase markdown files
  parsers/
    __init__.py                     TreeSitterParser -- Strategy pattern dispatcher
    base.py                         ASTNode dataclass + LanguageParser ABC
    python_parser.py                Python: functions, async functions, classes, methods
    javascript_parser.py            JavaScript: functions, classes, arrow functions
    typescript_parser.py            TypeScript: functions, classes, interfaces, types
    rust_parser.py                  Rust: functions, impl methods, structs, enums, traits
    go_parser.py                    Go: functions, methods (with receiver), structs, interfaces
    java_parser.py                  Java: classes, methods, constructors, interfaces
    cpp_parser.py                   C/C++: functions, classes, structs
    languages.yaml                  Extension-to-language mapping

main.py                             Legacy MCP server entry point (still works)
benchmark.py                        Benchmark tool -- semantic vs grep vs glob
tests/                              70 pytest tests
  test_chunker.py
  test_database.py
  test_search.py
  test_parser.py
  test_config.py
  test_encryption.py
  test_secret_scanner.py
  test_path_security.py
```

## How It Works

### Tree-sitter Chunking

Source files are parsed into ASTs via tree-sitter using a Strategy pattern -- each language has a dedicated parser class (`PythonParser`, `JavaScriptParser`, etc.) that extracts language-specific node types (functions, classes, methods, etc.). Chunks under 3 lines are skipped. Docstrings are prepended to their parent node for context. Files for unsupported languages are stored as whole files. File walking uses `ProcessPoolExecutor` with up to 8 workers for parallel chunking. Each chunk has a per-file timeout (30s) and a max file size limit (10MB).

### Embedding

Uses `sentence-transformers` with a configurable model (default `all-MiniLM-L6-v2`). An `OrderedDict`-based LRU cache avoids re-embedding repeated queries. The server calls `warm_up()` on startup to pre-load the model into memory. Supports offline mode and optional model SHA-256 verification.

### Database

Chunks are stored in LanceDB tables named `{codebase_name}_index`. Each table has a full-text search index on the `text` column. A Merkle tree tracks per-file MD5 hashes and per-directory composite hashes. The `update_codebase` function builds the current tree, compares it against the saved state, and only re-indexes changed or new files. Unchanged files are skipped entirely.

### Hybrid Search

Vector similarity search and full-text search are run in parallel (3x candidates each), then merged using Reciprocal Rank Fusion (RRF, k=60). RRF assigns a score to each document: `sum(1 / (k + rank + 1))` across both result sets. The merged results are sorted by combined score and truncated to the requested count. Falls back to vector-only search if FTS is unavailable.

### File Watching

Watchdog monitors file system events with a 2-second debounce timer. Modifications, creations, and deletions are handled per-file -- old chunks are deleted and the file is re-chunked and re-embedded. The watcher runs as a daemon thread alongside the MCP server.

### Config

`.codeindex.yml` is auto-discovered by walking up from the current directory to the git root. On first run, an interactive setup wizard detects the git repo and offers to index it, the current directory, or manually entered paths. The config file specifies codebases (name + root), file extensions, and exclude patterns.

### Security

Path validation prevents directory traversal attacks. Secret scanning detects and redacts 25+ patterns including AWS keys, JWTs, private keys, and high-entropy strings. LanceDB can be encrypted at rest using Fernet symmetric encryption with PBKDF2 key derivation (480,000 iterations). See the [Security](#security) section below for full details.

## Supported Languages

| Language | Chunking Strategy |
|----------|-------------------|
| Python | tree-sitter AST -- functions, async functions, classes, methods (with docstrings) |
| JS/TS | tree-sitter AST -- functions, classes, methods, arrow functions, interfaces, types |
| Rust | tree-sitter AST -- functions, impl methods, structs, enums, traits |
| Go | tree-sitter AST -- functions, methods (with receiver), structs, interfaces |
| Java | tree-sitter AST -- classes, methods, constructors, interfaces |
| C/C++ | tree-sitter AST -- functions, classes, structs |
| Other | Stored as whole file |

## MCP Tools

| Tool | Description |
|------|-------------|
| `search_code_tool(query, codebase_name, n_results=3)` | Hybrid search returning top-N results with file, line, name, type, score |
| `list_codebases()` | List all indexed codebases with chunk counts |
| `remove_codebase(codebase_name)` | Delete a codebase and its indexed data |

## Configuration

### `.codeindex.yml`

```yaml
codebases:
  - name: my_project
    root: ./src
  - name: other_project
    root: ./other

extensions:
  - .py
  - .js
  - .jsx
  - .ts
  - .tsx
  - .md
  - .txt
  - .json
  - .sql

exclude:
  - node_modules
  - .venv
  - __pycache__
  - .git
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CODE_INDEX_DB_PATH` | `./code_index_db` | Path to LanceDB persistence directory |
| `CODE_INDEX_N_RESULTS` | `3` | Default number of search results |
| `CODE_INDEX_EXTENSIONS` | `.py,.js,.jsx,.ts,.tsx,.md,.txt,.json,.sql` | File extensions to index |
| `CODE_INDEX_DEBOUNCE` | `2` | Watcher debounce time in seconds |
| `CODE_INDEX_EMBEDDING_CACHE_SIZE` | `512` | LRU cache size for query embeddings |
| `CODE_INDEX_EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | sentence-transformers model name |
| `CODE_INDEX_EMBEDDING_MODEL_SHA256` | (empty) | Optional model hash for verification |
| `CODE_INDEX_EMBEDDING_OFFLINE` | `false` | Use cached model, no downloads |
| `CODE_INDEX_ALLOWED_DIRS` | (current dir) | Comma-separated list of allowed root directories |
| `CODE_INDEX_MAX_FILE_SIZE_MB` | `10` | Max file size for chunking in MB |
| `CODE_INDEX_DB_ENCRYPTION_KEY` | (auto-generated) | Fernet key for encryption at rest (auto-generated on `setup`) |
| `CODE_INDEX_AUDIT_DIR` | (empty) | Directory for audit log files (enables audit logging when set) |

## Testing

```bash
uv run pytest tests/ -v
```

70 tests covering:

- **Chunking** -- tree-sitter AST splitting across all supported languages, docstrings, min-line filtering, process pool, timeouts
- **Database** -- LanceDB initialization, indexing with file hashes, Merkle tree change detection, incremental updates
- **Search** -- hybrid search, RRF merging, structured result formatting
- **Parser** -- question file parsing, section extraction
- **Config** -- YAML loading, config discovery, codebase resolution
- **Encryption** -- Fernet encrypt/decrypt, key derivation, full DB encryption round-trip
- **Path Security** -- directory traversal prevention, allowed directory enforcement
- **Secret Scanning** -- pattern matching, entropy detection, redaction

## Security

> See [`security.md`](security.md) for the full threat model, design decisions, and operational guidance.

### Key Security Features

| Feature | Description |
|---------|-------------|
| **Encryption at rest** | LanceDB data encrypted with Fernet symmetric encryption (PBKDF2, 480k iterations). Encryption key is auto-generated on first `setup` run and stored in `.env`. |
| **Secret scanning** | Detects and redacts 25+ secret patterns: AWS access/secret keys, JWTs, database URLs, GitHub/Slack/GitLab tokens, private keys, generic API keys, passwords, and high-entropy strings (Shannon entropy). |
| **Input validation** | All MCP tool endpoints validate inputs — path traversal is blocked, codebase names are sanitized, and queries are length-checked. |
| **Audit logging** | Optional audit trail of all MCP tool invocations, including timestamps, tool names, parameters, and results. Enable by setting `CODE_INDEX_AUDIT_DIR`. |
| **Symlink protection** | Symlinks are resolved and validated against allowed directories before any file read or index operation. |
| **Model integrity** | Optional SHA-256 verification of the embedding model to detect tampering or supply-chain attacks. Enable by setting `CODE_INDEX_EMBEDDING_MODEL_SHA256`. |

### Security Environment Variables

| Variable | Purpose |
|----------|---------|
| `CODE_INDEX_DB_ENCRYPTION_KEY` | Fernet key for encryption at rest. **Auto-generated** by `uv run code-index setup` — no manual configuration needed. |
| `CODE_INDEX_EMBEDDING_MODEL_SHA256` | Expected SHA-256 hash of the embedding model. Set to enable model integrity verification. |
| `CODE_INDEX_AUDIT_DIR` | Path to a directory for audit log files. Audit logging is enabled when this variable is set. |
| `CODE_INDEX_ALLOWED_DIRS` | Comma-separated list of directories the MCP server is permitted to access. Blocks access outside these roots. |
| `CODE_INDEX_EMBEDDING_OFFLINE` | When `true`, uses only cached models — prevents unexpected downloads at runtime. |

## Benchmark Results

Run benchmarks with:

```bash
uv run benchmark.py
```

Compares semantic search against grep and glob across all 220 questions from `questions.md` (196 with extractable targets). Results are exported to `benchmark_results.md`. Latest results:

| Metric | Semantic (LanceDB) | Grep | Glob |
|--------|---------------------|------|------|
| Top-1 Accuracy | 41.3% (81/196) | 3.1% (6/196) | 3.1% (6/196) |
| Top-3 Accuracy | 46.9% (92/196) | 7.7% (15/196) | 4.1% (8/196) |
| Top-5 Accuracy | 50.0% (98/196) | 10.2% (20/196) | 4.1% (8/196) |
| Avg Time (ms) | ~117 | ~70 | ~2.5 |

Semantic search dramatically outperforms grep and glob on natural language queries. The 50% top-5 rate reflects the difficulty of the 220-question suite, which includes cross-project references, route definitions, and config lookups that require understanding context beyond a single codebase.
