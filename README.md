# Semantic Code Search -- Semantic Code Search Engine with MCP Interface

Semantic Code Search is a semantic code search engine that lets AI agents find code by natural language queries instead of keyword matching. It indexes source files into a local vector database, enabling fast and accurate code retrieval powered by the `all-MiniLM-L6-v2` embedding model. The project exposes its search capabilities through an MCP (Model Context Protocol) server, a CLI, and a background file watcher for live indexing.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                       Semantic Code Search Architecture                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────┐     ┌──────────────┐     ┌───────────────────┐   │
│  │ Source Files  │────>│   Chunker    │────>│     ChromaDB      │   │
│  │ (.py .js .ts) │     │ (AST+Regex)  │     │  (Vector Store)   │   │
│  └──────────────┘     └──────────────┘     └─────────┬─────────┘   │
│                                                       │             │
│                     ┌─────────────────────────────────┤             │
│                     │                                 │             │
│               ┌─────▼──────┐   ┌──────────────┐  ┌───▼─────────┐  │
│               │ MCP Server  │   │   Watcher    │  │     CLI      │  │
│               │ (FastMCP)   │   │  (Watchdog)  │  │ (main.py)    │  │
│               │  4 tools    │   │  Debounced   │  │ Questions    │  │
│               └──────┬──────┘   └──────────────┘  └──────┬──────┘  │
│                      │                                  │          │
│               ┌──────▼──────┐                           │          │
│               │  AI Agents  │<──────────────────────────┘          │
│               │ (opencode / │                                      │
│               │   Claude)   │                                      │
│               └─────────────┘                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Key Features

- **Semantic search** -- find code using natural language queries, not keywords
- **AST-aware chunking** -- Python files are split into functions/classes via the `ast` module; JS/TS files via regex
- **Incremental updates** -- only re-indexes files that changed (MD5 hash comparison)
- **Background watcher** -- monitors file changes with debounced, per-file updates via Watchdog
- **MCP server** -- exposes index, search, list, and remove tools for AI agent integration
- **Embedding cache** -- LRU cache avoids re-embedding repeated queries
- **Benchmark suite** -- compares semantic search vs grep vs glob across 20 test queries

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11+ |
| Vector DB | ChromaDB (local, persistent) |
| Embeddings | `all-MiniLM-L6-v2` (via ChromaDB default) |
| MCP Server | FastMCP (`mcp[cli]`) |
| File Watching | Watchdog |
| Caching | `OrderedDict` LRU (embedder.py) |
| Config | python-dotenv |
| Testing | pytest |

## Quick Start

### Install

```bash
uv sync
```

### Index a Codebase

```bash
# Via CLI (indexes all codebases defined in main.py)
uv run main.py

# Via MCP tool (from an AI agent)
index_codebase_tool(codebase_name="my_project", root_dir="./src")
```

### Search

```bash
# Via CLI (runs questions from questions.md)
uv run main.py

# Via MCP tool
search_code_tool(query="Where is the authentication logic?", codebase_name="my_project")

# Via Python
from code_index import init_client, get_collection, search_code
client = init_client("./code_index_db")
collection = get_collection(client, "my_project_index")
result = search_code("authentication logic", collection)
```

### Watch for Changes

```bash
# With CLI args
uv run watcher.py --watch my_project=./src --watch other_project=./other

# With config file
uv run watcher.py --config watch_config.json
```

### Start the MCP Server

```bash
# Development mode
uv run mcp dev server.py

# Production
uv run server.py
```

## Project Structure

```
code_index/                 Core library
  __init__.py               Re-exports public API
  config.py                 Environment variable configuration (dotenv)
  chunker.py                AST chunking (Python), regex chunking (JS/TS), file walker
  embedder.py               Embedding function with LRU cache + warm-up
  database.py               ChromaDB client, indexing, incremental updates (MD5)
  search.py                 Semantic search with structured result formatting
  parser.py                 Parses questions.md into per-codebase question lists
  exporter.py               Writes search results to per-codebase markdown files

server.py                   MCP server (FastMCP) -- 4 tools
watcher.py                  Background file watcher (Watchdog) -- debounced updates
main.py                     CLI entry point -- indexes codebases, runs questions
benchmark.py                Semantic vs grep vs glob comparison (20 test queries)
watch_config.json           Sample watcher configuration

tests/                      28 pytest tests
  test_chunker.py           Python AST chunking, JS/TS regex chunking, file walking
  test_database.py          ChromaDB indexing, incremental updates, hash comparison
  test_search.py            Semantic search, structured results, formatting
  test_parser.py            Question file parsing (sections, mappings)

questions.md                220 interview questions across 4 codebases
test_codebase/              4 sample codebases for indexing and benchmarking
  card_shop/                Pokemon TCG card shop (FastAPI backend)
  card_collection/          Card collection manager
  card_infrastructure/      TCGPlayer pricing database + eBay scraper
  financial_visuals/        Financial data analysis and charts
```

## How It Works

### Chunking (`code_index/chunker.py`)

Python files are parsed with the `ast` module and split into individual functions, async functions, and classes. Chunks under 3 lines are skipped, and docstrings are prepended for context. JS/TS files are parsed with regex patterns that extract functions, classes, arrow functions, interfaces, and type aliases. Other files (`.md`, `.json`, `.sql`, `.txt`) are stored as whole files. File walking uses `ProcessPoolExecutor` with up to 8 workers for parallel chunking.

### Embedding (`code_index/embedder.py`)

Uses ChromaDB's built-in `all-MiniLM-L6-v2` embedding function with an LRU cache (`OrderedDict`) to avoid re-embedding repeated queries. The server calls `warm_up()` on startup to pre-load the model.

### Database (`code_index/database.py`)

Stores chunks in persistent ChromaDB collections named `{codebase_name}_index`. Each chunk's metadata includes an MD5 file hash for incremental update support. The `update_codebase` function walks the directory, compares hashes against stored metadata, and only re-indexes changed or new files.

### Search (`code_index/search.py`)

Queries are embedded and matched against stored vectors via L2 distance. Returns structured results with file path, line number, name, type, distance score, and source code. Lower distance indicates a better match.

### Watcher (`watcher.py`)

Uses Watchdog to monitor file system events with a configurable debounce timer (default 2 seconds). On startup, it full-indexes empty collections and runs incremental updates on existing ones. File modifications, creations, and deletions are handled per-file with automatic chunk cleanup and re-indexing.

### MCP Server (`server.py`)

Exposes 4 tools over the MCP protocol for AI agent integration. Pre-warms the embedding model on startup and caches collection references for performance.

## Configuration

Create a `.env` file (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `CODE_INDEX_DB_PATH` | `./code_index_db` | Path to ChromaDB persistence directory |
| `CODE_INDEX_N_RESULTS` | `3` | Default number of search results |
| `CODE_INDEX_EXTENSIONS` | `.py,.js,.jsx,.ts,.tsx,.md,.txt,.json,.sql` | File extensions to index |
| `CODE_INDEX_DEBOUNCE` | `2` | Watcher debounce time in seconds |
| `CODE_INDEX_EMBEDDING_CACHE_SIZE` | `512` | LRU cache size for query embeddings |

Watcher config (`watch_config.json`):

```json
{
  "codebases": [
    { "name": "my_project", "root": "./src" },
    { "name": "other_project", "root": "./other" }
  ]
}
```

## MCP Tools

| Tool | Description |
|------|-------------|
| `index_codebase_tool(codebase_name, root_dir)` | Full index of a directory (drops existing collection first) |
| `search_code_tool(query, codebase_name, n_results=3)` | Semantic search returning top-N results |
| `list_codebases()` | List all indexed collections with chunk counts |
| `remove_codebase(codebase_name)` | Delete a codebase collection |

## Benchmark Results

Run benchmarks with:

```bash
uv run benchmark.py
```

Compares semantic search against grep and glob across all 220 questions from `questions.md` (196 with extractable targets). Results are exported to `benchmark_results.md`. Latest results:

| Metric | Semantic (ChromaDB) | Grep | Glob |
|--------|---------------------|------|------|
| Top-1 Accuracy | 41.3% (81/196) | 3.1% (6/196) | 3.1% (6/196) |
| Top-3 Accuracy | 46.9% (92/196) | 7.7% (15/196) | 4.1% (8/196) |
| Top-5 Accuracy | 50.0% (98/196) | 10.2% (20/196) | 4.1% (8/196) |
| Avg Time (ms) | ~117 | ~70 | ~2.5 |

Semantic search dramatically outperforms grep and glob on natural language queries. The 50% top-5 rate reflects the difficulty of the 220-question suite, which includes cross-project references, route definitions, and config lookups that require understanding context beyond a single codebase.

## Testing

```bash
uv run pytest tests/ -v
```

28 tests covering:

- **Chunking** (16 tests) -- Python AST splitting, JS/TS regex extraction, docstrings, syntax errors, min-line filtering, file walking, export patterns, interfaces, type aliases, class inheritance
- **Database** (6 tests) -- client initialization, collection creation, indexing with file hashes, incremental updates for new/changed/unchanged files
- **Search** (4 tests) -- structured result format, result keys, human-readable formatting, correct function retrieval
- **Parser** (3 tests) -- question extraction, infrastructure section mapping, multiple codebase sections

## Supported File Types

| Extension | Chunking Strategy |
|-----------|-------------------|
| `.py` | AST -- functions, async functions, classes (with docstrings) |
| `.js`, `.jsx`, `.ts`, `.tsx` | Regex -- functions, classes, arrow functions, interfaces, type aliases |
| `.md`, `.txt`, `.json`, `.sql` | Stored as whole file |
