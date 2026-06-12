from __future__ import annotations

import os
import socket
import sys
import time
from datetime import datetime

import click
from mcp.server.fastmcp import FastMCP

from code_index.config import DB_PATH, EMBEDDING_CACHE_SIZE, PERIODIC_REINDEX_SECONDS
from code_index.chunker import get_file_paths, split_with_treesitter
from code_index.database import init_client, get_collection, index_codebase, update_codebase
from code_index.search import search_code
from code_index.embedder import init_embedder, warm_up
from code_index.path_security import validate_root_dir
from code_index.config_loader import get_codebases_from_config, get_exclude_from_config, find_config_file
from code_index.config_setup import run_setup, quick_setup
from code_index import watcher
from code_index.query_sanitizer import sanitize_query, validate_codebase_name, validate_n_results
from code_index.audit import init_audit_log, log_search, log_list_codebases, log_remove_codebase, log_error, log_security_event

_db = None
_tables = {}


def _startup():
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] code-index ready", file=sys.stderr)


def _resolve_db_path():
    if os.path.isabs(DB_PATH):
        return DB_PATH
    cfg = find_config_file()
    if cfg:
        return os.path.join(os.path.dirname(cfg), DB_PATH)
    return DB_PATH


def _get_db():
    global _db
    if _db is None:
        _db = init_client(_resolve_db_path())
    return _db


def _codebase_name(root_dir):
    return os.path.basename(os.path.abspath(root_dir))


def _table_name(root_dir):
    return f"{_codebase_name(root_dir)}_index"


def _get_table(name):
    if name not in _tables:
        _tables[name] = get_collection(_get_db(), name)
    return _tables[name]


def _list_indexed_tables():
    db = _get_db()
    pairs = []
    for t in db.list_tables():
        name = t[0] if isinstance(t, tuple) else str(t)
        if name.endswith("_index"):
            display = name.replace("_index", "")
            pairs.append((display, _get_table(name)))
    return pairs


def _resolve_codebases():
    config_cbs = get_codebases_from_config()
    if config_cbs:
        return config_cbs
    print("No .codeindex.yml found. Let's set one up.\n")
    return run_setup()


def _init_embedder():
    init_embedder(cache_size=EMBEDDING_CACHE_SIZE)
    warm_up()


def _index_codebase(name, root, quick=False, exclude_dirs=None):
    root = validate_root_dir(root)
    tbl_name = _table_name(root)
    table = _get_table(tbl_name)
    db_path = _resolve_db_path()

    if table.count_rows() == 0:
        if quick:
            print(f"[{name}] Quick mode — skipping initial index, building in background")
            from code_index.database import MerkleTree, _save_merkle_state
            merkle_tree = MerkleTree(root, exclude_dirs=exclude_dirs)
            _save_merkle_state(db_path, name, merkle_tree)
            return table
        print(f"[{name}] Chunking files...")
        chunks = get_file_paths(root, exclude_dirs=exclude_dirs)
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] [{name}] Full index: {len(chunks)} chunks from {root}")
        from code_index.database import MerkleTree
        merkle_tree = MerkleTree(root, exclude_dirs=exclude_dirs)
        index_codebase(chunks, table, db_path=db_path, codebase_name=name, merkle_tree=merkle_tree)
    else:
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] [{name}] Checking for changes...")
        t0 = time.time()
        update_codebase(root, table, split_with_treesitter, db_path=db_path, codebase_name=name, exclude_dirs=exclude_dirs)
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] [{name}] Incremental update done ({table.count_rows()} chunks, {time.time() - t0:.1f}s)")
    return table


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx):
    if ctx.invoked_subcommand is None:
        ctx.invoke(serve)


def _get_lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0.1)
    try:
        s.connect(("10.254.254.254", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


@main.command(help="""
Start the MCP server — index configured codebases, watch files, and serve
search queries over SSE.

Run this in a terminal and leave it running to keep the model warm.
Connect your AI agent (Claude Code, Cursor, opencode, etc.) to the SSE URL.

Reads .codeindex.yml from the current directory (walks up to git root).
If no config is found, launches the interactive setup wizard automatically.

Examples:

  code-index serve                         # start SSE server on :1337
  code-index serve --port 8080             # custom port
  code-index serve --quick                 # skip initial index, build in background

  --transport: sse (default), stdio, or streamable-http
               sse connects via HTTP (recommended for persistent servers)
               stdio connects via stdin/stdout (for spawned processes)

  See README.md for MCP connection instructions for your AI tool.
""")
@click.option("--transport", default="sse", show_default=True,
              type=click.Choice(["sse", "stdio", "streamable-http"]))
@click.option("--host", default=None, help="Bind address for SSE/HTTP transports (default: 127.0.0.1)")
@click.option("--port", default=1337, type=int, help="Port for SSE/HTTP transports (default: 1337)")
@click.option("--quick", is_flag=True, help="Skip initial index, build in background")
def serve(transport, host, port, quick):
    _startup()
    _init_embedder()
    codebases = _resolve_codebases()
    exclude_dirs = get_exclude_from_config()
    watcher_codebases = []

    for cb in codebases:
        table = _index_codebase(cb["name"], cb["root"], quick=quick, exclude_dirs=exclude_dirs)
        watcher_codebases.append({
            "name": cb["name"],
            "root": cb["root"],
            "table": table,
        })

    if watcher_codebases:
        watcher.start_watcher(watcher_codebases)
        watcher.start_periodic_reindex(watcher_codebases, _resolve_db_path(), exclude_dirs=exclude_dirs)

    mcp_kwargs = {"name": "code_index"}
    if host:
        mcp_kwargs["host"] = host
    if port:
        mcp_kwargs["port"] = port
    mcp = FastMCP(**mcp_kwargs)
    init_audit_log()

    effective_host = host or "127.0.0.1"
    effective_port = port
    print(file=sys.stderr)
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] MCP server ready", file=sys.stderr)
    if transport == "stdio":
        print("  Transport: stdio", file=sys.stderr)
        print(file=sys.stderr)
        print("  Connect your AI agent:", file=sys.stderr)
        print(f"    claude mcp add code-index -- uv run --directory {os.getcwd()} python -m code_index", file=sys.stderr)
    else:
        suffix = "/sse" if transport == "sse" else "/mcp"
        lan_ip = _get_lan_ip()
        loopback_url = f"http://127.0.0.1:{effective_port}{suffix}"
        lan_url = f"http://{lan_ip}:{effective_port}{suffix}"
        print(f"  Transport: {transport}", file=sys.stderr)
        print(f"  Loopback:  {loopback_url}", file=sys.stderr)
        if lan_ip != "127.0.0.1":
            print(f"  LAN:       {lan_url}", file=sys.stderr)
        print(file=sys.stderr)
        print("  Connect your AI agent:", file=sys.stderr)
        print(f"    claude mcp add code-index sse --url {loopback_url}", file=sys.stderr)
        print(f"    opencode mcp add code-index   # interactive, select remote, enter URL: {loopback_url}", file=sys.stderr)
    print(file=sys.stderr)

    @mcp.tool()
    def search_code_tool(query: str, codebase_name: str | None = None, n_results: int = 3) -> str:
        try:
            query = sanitize_query(query)
            n_results = validate_n_results(n_results)
        except ValueError as e:
            log_security_event("invalid_search_input", str(e))
            return f"Invalid input: {e}"
        try:
            if codebase_name:
                codebase_name = validate_codebase_name(codebase_name)
                tables_to_search = [(codebase_name, _get_table(f"{codebase_name}_index"))]
            else:
                tables_to_search = _list_indexed_tables()

            all_results = []
            for name, table in tables_to_search:
                if table.count_rows() == 0:
                    continue
                result = search_code(query, table, n_results)
                for r in result["results"]:
                    r["_codebase"] = name
                all_results.extend(result["results"])

            if not all_results:
                return "No indexed codebases found."

            all_results.sort(key=lambda r: r["distance"])
            top = all_results[:n_results]

            log_search(query, codebase_name or "all", n_results, len(all_results))
            lines = [f'Query: "{query}"', "=" * 60]
            for i, r in enumerate(top):
                lines.append(f"--- Result {i + 1} ---")
                lines.append(f"Codebase: {r['_codebase']}")
                lines.append(f"File:     {r['file']}")
                lines.append(f"Line:     {r['start_line']}")
                lines.append(f"Name:     {r['name']}")
                lines.append(f"Type:     {r['type']}")
                lines.append(f"Score:    {r['distance']:.4f}")
                lines.append(f"Code:\n{r['code']}")
                lines.append("-" * 60)
            return "\n".join(lines)
        except Exception as e:
            log_error("search_code", type(e).__name__)
            return f"Error: search failed — {e}"

    @mcp.tool()
    def list_codebases() -> str:
        try:
            db = _get_db()
            raw_tables = db.list_tables()
            table_names = []
            for t in raw_tables:
                name = t[0] if isinstance(t, tuple) else str(t)
                if name.endswith("_index"):
                    table_names.append(name)
            log_list_codebases(len(table_names))
            results = []
            for tbl_name in table_names:
                t = db.open_table(tbl_name)
                count = t.count_rows()
                display_name = tbl_name.replace("_index", "")
                results.append(f"  {display_name}: {count} chunks")
            if not results:
                return "No indexed codebases found."
            return "Indexed codebases:\n" + "\n".join(results)
        except Exception as e:
            log_error("list_codebases", f"{type(e).__name__}: {e}")
            return f"Error listing codebases: {e}"

    @mcp.tool()
    def remove_codebase(codebase_name: str) -> str:
        try:
            codebase_name = validate_codebase_name(codebase_name)
        except ValueError as e:
            log_security_event("invalid_remove_input", str(e))
            return f"Invalid input: {e}"
        try:
            tbl_name = f"{codebase_name}_index"
            _get_db().drop_table(tbl_name)
            if tbl_name in _tables:
                del _tables[tbl_name]
            log_remove_codebase(codebase_name, True)
            return f"Removed codebase '{codebase_name}'."
        except Exception as e:
            log_remove_codebase(codebase_name, False)
            log_error("remove_codebase", type(e).__name__)
            return "Error: could not remove codebase"

    mcp.run(transport=transport)


@main.command(name="index", help="""
Index or re-index configured codebases without starting the MCP server or
file watcher.

Reads .codeindex.yml from the current directory (walks up to git root).
If no config is found, launches the interactive setup wizard automatically.

Useful for batch indexing or CI pipelines.
""")
def index_cmd():
    _startup()
    _init_embedder()
    codebases = _resolve_codebases()
    for cb in codebases:
        root = validate_root_dir(cb["root"])
        table = get_collection(_get_db(), f"{cb['name']}_index")
        exclude_dirs = get_exclude_from_config()
        chunks = get_file_paths(root, exclude_dirs=exclude_dirs)
        print(f"[{cb['name']}] Indexing {len(chunks)} chunks from {root}")
        index_codebase(chunks, table, db_path=_resolve_db_path(), codebase_name=cb["name"])


@main.command(help="""
Configure a project for indexing.

Writes a .codeindex.yml config file and a .env with an encryption key in the
current directory. After this, code-index serve and code-index index will
know which project to use.

Examples:

  code-index setup ~/my-project
    Configure indexing for ~/my-project.

  code-index setup
    Interactive wizard — prompts for the project directory.
""")
@click.argument("path", default=None, required=False)
def setup(path):
    if path:
        if not os.path.isdir(path):
            print(f"Error: not a directory: {path}", file=sys.stderr)
            sys.exit(1)
        quick_setup(path)
    else:
        run_setup()


@main.command(help="""
Semantic code search against an indexed codebase.

Performs hybrid search (vector + full-text) using Reciprocal Rank Fusion.
Requires the codebase to be indexed first via code-index serve or code-index index.

Results include file path, line number, function/class name, and relevance score.

Examples:

  code-index search --query "api endpoint handler" --codebase myproject

  code-index search --query "database connection pool" --codebase myproject --n-results 5
""")
@click.option("--query", required=True, help="Natural language search query")
@click.option("--codebase", "codebase_name", required=True, help="Codebase name (matches name: in .codeindex.yml)")
@click.option("--n-results", "n_results", default=3, show_default=True, help="Number of results to return")
def search(query, codebase_name, n_results):
    _startup()
    _init_embedder()
    table = _get_table(f"{codebase_name}_index")
    result = search_code(query, table, n_results)
    from code_index.search import format_results
    print(format_results(result))
