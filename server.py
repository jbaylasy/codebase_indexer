from mcp.server.fastmcp import FastMCP
from code_index.config import DB_PATH, EMBEDDING_CACHE_SIZE
from code_index.chunker import get_file_paths
from code_index.database import init_client, get_collection, index_codebase
from code_index.search import search_code
from code_index.embedder import warm_up, init_embedder

mcp = FastMCP("code_index")

_db = init_client(DB_PATH)
_tables = {}
init_embedder(cache_size=EMBEDDING_CACHE_SIZE)
warm_up()


def _get_table(name):
    if name not in _tables:
        _tables[name] = get_collection(_db, name)
    return _tables[name]


@mcp.tool()
def index_codebase_tool(codebase_name: str, root_dir: str) -> str:
    try:
        table_name = f"{codebase_name}_index"
        existing = _db.list_tables()
        if table_name in existing:
            _db.drop_table(table_name)
            if table_name in _tables:
                del _tables[table_name]
        table = _get_table(table_name)
        chunks = get_file_paths(root_dir)
        index_codebase(chunks, table, db_path=DB_PATH, codebase_name=codebase_name)
        return f"Indexed {table.count_rows()} chunks into table '{table_name}'."
    except Exception as e:
        return f"Error indexing codebase: {e}"


@mcp.tool()
def search_code_tool(query: str, codebase_name: str, n_results: int = 3) -> str:
    try:
        table_name = f"{codebase_name}_index"
        table = _get_table(table_name)
        if table.count_rows() == 0:
            return f"Table '{table_name}' is empty."
        result = search_code(query, table, n_results)
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
        return f"Error searching code: {e}"


@mcp.tool()
def list_codebases() -> str:
    try:
        table_names = _db.list_tables()
        results = []
        for name in table_names:
            t = _db.open_table(name)
            count = t.count_rows()
            results.append(f"{name}: {count} chunks")
        if not results:
            return "No indexed codebases found."
        return "\n".join(results)
    except Exception as e:
        return f"Error listing codebases: {e}"


@mcp.tool()
def remove_codebase(codebase_name: str) -> str:
    try:
        table_name = f"{codebase_name}_index"
        _db.drop_table(table_name)
        if table_name in _tables:
            del _tables[table_name]
        return f"Removed table '{table_name}'."
    except Exception as e:
        return f"Error removing codebase: {e}"


if __name__ == "__main__":
    mcp.run()
