from mcp.server.fastmcp import FastMCP
from code_index.config import DB_PATH, EMBEDDING_CACHE_SIZE
from code_index.chunker import get_file_paths
from code_index.database import init_client, get_collection, index_codebase
from code_index.search import search_code
from code_index.embedder import warm_up, init_embedder

mcp = FastMCP("code_index")

_client = init_client(DB_PATH)
_collections = {}
init_embedder(cache_size=EMBEDDING_CACHE_SIZE)
warm_up()


def _get_collection(name):
    if name not in _collections:
        _collections[name] = get_collection(_client, name)
    return _collections[name]


@mcp.tool()
def index_codebase_tool(codebase_name: str, root_dir: str) -> str:
    try:
        collection_name = f"{codebase_name}_index"
        existing = _client.list_collections()
        if any(c.name == collection_name for c in existing):
            _client.delete_collection(collection_name)
            if collection_name in _collections:
                del _collections[collection_name]
        collection = _get_collection(collection_name)
        chunks = get_file_paths(root_dir)
        index_codebase(chunks, collection)
        return f"Indexed {collection.count()} chunks into collection '{collection_name}'."
    except Exception as e:
        return f"Error indexing codebase: {e}"


@mcp.tool()
def search_code_tool(query: str, codebase_name: str, n_results: int = 3) -> str:
    try:
        collection_name = f"{codebase_name}_index"
        collection = _get_collection(collection_name)
        if collection.count() == 0:
            return f"Collection '{collection_name}' is empty."
        result = search_code(query, collection, n_results)
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
        collections = _client.list_collections()
        results = []
        for col_info in collections:
            name = col_info.name
            col = _client.get_collection(name)
            count = col.count()
            results.append(f"{name}: {count} chunks")
        if not results:
            return "No indexed codebases found."
        return "\n".join(results)
    except Exception as e:
        return f"Error listing codebases: {e}"


@mcp.tool()
def remove_codebase(codebase_name: str) -> str:
    try:
        collection_name = f"{codebase_name}_index"
        _client.delete_collection(collection_name)
        if collection_name in _collections:
            del _collections[collection_name]
        return f"Removed collection '{collection_name}'."
    except Exception as e:
        return f"Error removing codebase: {e}"


if __name__ == "__main__":
    mcp.run()
