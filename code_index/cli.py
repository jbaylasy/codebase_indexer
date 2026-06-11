from __future__ import annotations

import os
import sys

import click
from mcp.server.fastmcp import FastMCP

from code_index.config import DB_PATH, EMBEDDING_CACHE_SIZE, PERIODIC_REINDEX_SECONDS
from code_index.chunker import get_file_paths, split_with_treesitter
from code_index.database import init_client, get_collection, index_codebase, update_codebase
from code_index.search import search_code
from code_index.embedder import init_embedder, warm_up
from code_index.path_security import validate_root_dir
from code_index.config_loader import get_codebases_from_config
from code_index.config_setup import run_setup
from code_index import watcher
from code_index.query_sanitizer import sanitize_query, validate_codebase_name, validate_n_results
from code_index.audit import init_audit_log, log_search, log_list_codebases, log_remove_codebase, log_error, log_security_event

_db = None
_tables = {}


def _startup():
    print("  code-index ready", file=sys.stderr)


def _get_db():
    global _db
    if _db is None:
        _db = init_client(DB_PATH)
    return _db


def _codebase_name(root_dir):
    return os.path.basename(os.path.abspath(root_dir))


def _table_name(root_dir):
    return f"{_codebase_name(root_dir)}_index"


def _get_table(name):
    if name not in _tables:
        _tables[name] = get_collection(_get_db(), name)
    return _tables[name]


def _resolve_codebases():
    config_cbs = get_codebases_from_config()
    if config_cbs:
        return config_cbs
    print("No .codeindex.yml found. Let's set one up.\n")
    return run_setup()


def _init_embedder():
    init_embedder(cache_size=EMBEDDING_CACHE_SIZE)
    warm_up()


def _index_codebase(name, root):
    root = validate_root_dir(root)
    tbl_name = _table_name(root)
    table = _get_table(tbl_name)

    if table.count_rows() == 0:
        chunks = get_file_paths(root)
        print(f"[{name}] Full index: {len(chunks)} chunks from {root}")
        index_codebase(chunks, table, db_path=DB_PATH, codebase_name=name)
    else:
        update_codebase(root, table, split_with_treesitter, db_path=DB_PATH, codebase_name=name)
        print(f"[{name}] Incremental update done ({table.count_rows()} chunks)")
    return table


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx):
    if ctx.invoked_subcommand is None:
        print(ctx.get_help())
        print()
        print("  Use a subcommand or run with no arguments to start the MCP server.")
        print()
        print("  Examples:")
        print("    code-index setup                    Interactive config wizard")
        print("    code-index setup --dir ~/myproject  Config for a project in another dir")
        print("    code-index serve                    Start MCP server with indexed code")
        print("    code-index search --query \"find api\" --codebase myproject")
        print()


@main.command(help="""
Start the MCP server — index codebases, watch files, and serve search queries.

Discovers codebases from .codeindex.yml in the current directory (walks up to
git root). If no config is found, launches the interactive setup wizard.

The server continuously watches files for changes and reindexes automatically.
A periodic full reindex also runs every 300s (configurable).

Examples:

  code-index serve
    Start the server using .codeindex.yml from cwd or git root.

  cd ~/myproject && code-index serve
    Serve a project by running from its directory.
""")
def serve():
    _startup()
    _init_embedder()
    codebases = _resolve_codebases()
    watcher_codebases = []

    for cb in codebases:
        table = _index_codebase(cb["name"], cb["root"])
        watcher_codebases.append({
            "name": cb["name"],
            "root": cb["root"],
            "table": table,
        })

    if watcher_codebases:
        watcher.start_watcher(watcher_codebases)
        watcher.start_periodic_reindex(watcher_codebases, DB_PATH)

    mcp = FastMCP("code_index")
    init_audit_log()

    @mcp.tool()
    def search_code_tool(query: str, codebase_name: str, n_results: int = 3) -> str:
        try:
            query = sanitize_query(query)
            codebase_name = validate_codebase_name(codebase_name)
            n_results = validate_n_results(n_results)
        except ValueError as e:
            log_security_event("invalid_search_input", str(e))
            return f"Invalid input: {e}"
        try:
            table = _get_table(f"{codebase_name}_index")
            if table.count_rows() == 0:
                return f"No indexed codebase found for '{codebase_name}'."
            result = search_code(query, table, n_results)
            log_search(query, codebase_name, n_results, len(result["results"]))
            lines = [f'Query: "{query}"', "=" * 60]
            for i, r in enumerate(result["results"]):
                lines.append(f"--- Result {i + 1} ---")
                lines.append(f"File:   {r['file']}")
                lines.append(f"Line:   {r['start_line']}")
                lines.append(f"Name:   {r['name']}")
                lines.append(f"Type:   {r['type']}")
                lines.append(f"Score:  {r['distance']:.4f}")
                lines.append(f"Code:\n{r['code']}")
                lines.append("-" * 60)
            return "\n".join(lines)
        except Exception as e:
            log_error("search_code", type(e).__name__)
            return "Error: search failed"

    @mcp.tool()
    def list_codebases() -> str:
        try:
            db = _get_db()
            table_names = db.list_tables()
            log_list_codebases(len(table_names))
            results = []
            for tbl_name in table_names:
                t = db.open_table(tbl_name)
                count = t.count_rows()
                results.append(f"{tbl_name}: {count} chunks")
            if not results:
                return "No indexed codebases found."
            return "\n".join(results)
        except Exception as e:
            log_error("list_codebases", type(e).__name__)
            return "Error: could not list codebases"

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

    mcp.run()


@main.command(name="index", help="""
Index or re-index codebases without starting the MCP server.

Reads codebase configuration from .codeindex.yml, scans all files, chunks them
using tree-sitter, and stores embeddings in LanceDB.

Useful for batch indexing without the server overhead.

Examples:

  code-index index
    Index all codebases defined in .codeindex.yml (found from cwd or git root).
""")
def index_cmd():
    _startup()
    _init_embedder()
    codebases = _resolve_codebases()
    for cb in codebases:
        root = validate_root_dir(cb["root"])
        table = get_collection(_get_db(), f"{cb['name']}_index")
        chunks = get_file_paths(root)
        print(f"[{cb['name']}] Indexing {len(chunks)} chunks from {root}")
        index_codebase(chunks, table, db_path=DB_PATH, codebase_name=cb["name"])


@main.command(help="""
Interactive one-time setup wizard for a new project.

Walks you through choosing a codebase directory, writes a .codeindex.yml config
file and a .env with an encryption key. Run this once per project before
code-index serve or code-index index.

The config is saved in the current directory (or --dir if provided). Config
auto-discovery walks up from cwd to find .codeindex.yml at runtime, so run
serve/index from the same directory where you ran setup.

Examples:

  cd ~/myproject && code-index setup
    Create .codeindex.yml for the project in ~/myproject.

  code-index setup --dir ~/myproject
    Same, but run from any directory by passing --dir.

  code-index setup
    Run from any directory and use option 3 to type paths manually.
""")
@click.option("-d", "--dir", "target_dir", default=None,
              help="Target project directory. Config is saved here. Defaults to cwd.")
def setup(target_dir):
    run_setup(start_dir=target_dir)


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
