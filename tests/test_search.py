from code_index.search import search_code, format_results
from code_index.database import init_client, get_collection, index_codebase


def _setup_collection(tmp_path):
    py_file = tmp_path / "search_target.py"
    py_file.write_text(
        "def calculate_total(items):\n"
        "    total = 0\n"
        "    for item in items:\n"
        "        total += item['price']\n"
        "    return total\n"
    )
    client = init_client(str(tmp_path / "chroma"))
    collection = get_collection(client, "test_search")
    chunks = [
        {
            "text": (
                "def calculate_total(items):\n"
                "    total = 0\n"
                "    for item in items:\n"
                "        total += item['price']\n"
                "    return total\n"
            ),
            "metadata": {
                "file": str(py_file),
                "start_line": 1,
                "type": "function",
                "name": "calculate_total",
            },
        }
    ]
    index_codebase(chunks, collection)
    return collection


def test_search_code_returns_structured_results(tmp_path):
    collection = _setup_collection(tmp_path)
    result = search_code("calculate total price", collection)
    assert "query" in result
    assert "results" in result
    assert "raw" in result
    assert result["query"] == "calculate total price"


def test_search_code_result_keys(tmp_path):
    collection = _setup_collection(tmp_path)
    result = search_code("calculate total", collection)
    assert len(result["results"]) >= 1
    r = result["results"][0]
    for key in ("file", "start_line", "name", "type", "distance", "code"):
        assert key in r


def test_format_results(tmp_path):
    collection = _setup_collection(tmp_path)
    result = search_code("total", collection)
    formatted = format_results(result)
    assert 'Query: "total"' in formatted
    assert "--- Result 1 ---" in formatted
    assert "File:" in formatted
    assert "calculate_total" in formatted


def test_search_finds_correct_function(tmp_path):
    collection = _setup_collection(tmp_path)
    result = search_code("calculate total of items", collection)
    assert len(result["results"]) >= 1
    assert result["results"][0]["name"] == "calculate_total"
    assert "total" in result["results"][0]["code"]
