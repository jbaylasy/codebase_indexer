from __future__ import annotations

import os

import click
from mcp.server.fastmcp import FastMCP

from code_index.config import DB_PATH, EMBEDDING_CACHE_SIZE, PERIODIC_REINDEX_SECONDS
from code_index.chunker import get_file_paths
from code_index.database import init_client, get_collection, index_codebase, update_codebase
from code_index.search import search_code
from code_index.embedder import warm_up, init_embedder
from code_index.path_security import validate_root_dir
from code_index.config_loader import get_codebases_from_config
from code_index.config_setup import run_setup
from code_index import watcher as _watcher
from code_index.query_sanitizer import sanitize_query, validate_codebase_name, validate_n_results
from code_index.audit import init_audit_log, log_search, log_list_codebases, log_remove_codebase, log_error, log_security_event

_db = None
_tables = {}


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
        from code_index.chunker import split_with_treesitter

        update_codebase(root, table, split_with_treesitter, db_path=DB_PATH, codebase_name=name)
        print(f"[{name}] Incremental update done ({table.count_rows()} chunks)")
    return table


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx):
    if ctx.invoked_subcommand is None:
        ctx.invoke(serve)


@main.command()
def serve():
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
        _watcher.start_watcher(watcher_codebases)
        _watcher.start_periodic_reindex(watcher_codebases, DB_PATH)

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


@main.command(name="index")
def index_cmd():
    _init_embedder()
    codebases = _resolve_codebases()
    for cb in codebases:
        _index_codebase(cb["name"], cb["root"])


@main.command()
def setup():
    run_setup()


@main.command()
@click.option("--query", required=True, help="Search query")
@click.option("--codebase", "codebase_name", required=True, help="Codebase name to search")
def search(query, codebase_name):
    _init_embedder()
    table = _get_table(f"{codebase_name}_index")
    result = search_code(query, table)
    from code_index.search import format_results
    print(format_results(result))
