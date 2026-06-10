import os
import hashlib
import chromadb
from code_index.database import init_client, get_collection, index_codebase, update_codebase


def test_init_client(tmp_path):
    client = init_client(str(tmp_path / "test_db"))
    assert hasattr(client, "get_or_create_collection")
    assert hasattr(client, "list_collections")


def test_get_collection(tmp_path):
    client = init_client(str(tmp_path / "test_db"))
    collection = get_collection(client, "test_col")
    assert collection.name == "test_col"


def test_index_codebase_adds_chunks_with_file_hash(tmp_path):
    py_file = tmp_path / "sample.py"
    py_file.write_text(
        "def greet(name):\n"
        "    msg = f'Hello {name}'\n"
        "    return msg\n"
    )
    client = init_client(str(tmp_path / "chroma"))
    collection = get_collection(client, "test_idx")
    chunks = [
        {
            "text": "def greet(name):\n    msg = f'Hello {name}'\n    return msg\n",
            "metadata": {
                "file": str(py_file),
                "start_line": 1,
                "type": "function",
                "name": "greet",
            },
        }
    ]
    index_codebase(chunks, collection)
    assert collection.count() == 1
    result = collection.get(include=["metadatas"])
    assert result["metadatas"][0]["file_hash"] != ""


def test_update_codebase_detects_new_files(tmp_path):
    client = init_client(str(tmp_path / "chroma"))
    collection = get_collection(client, "test_update_new")

    new_file = tmp_path / "new_module.py"
    new_file.write_text(
        "def compute(x):\n"
        "    y = x * 2\n"
        "    return y\n"
    )
    from code_index.chunker import split_python_code
    update_codebase(str(tmp_path), collection, split_python_code)
    assert collection.count() >= 1


def test_update_codebase_detects_changed_files(tmp_path):
    client = init_client(str(tmp_path / "chroma"))
    collection = get_collection(client, "test_update_changed")

    py_file = tmp_path / "mod.py"
    py_file.write_text(
        "def original():\n"
        "    a = 1\n"
        "    return a\n"
    )
    from code_index.chunker import split_python_code
    update_codebase(str(tmp_path), collection, split_python_code)
    assert collection.count() >= 1

    py_file.write_text(
        "def changed():\n"
        "    b = 2\n"
        "    return b\n"
    )
    update_codebase(str(tmp_path), collection, split_python_code)

    all_meta = collection.get(include=["metadatas"])
    names = [m["name"] for m in all_meta["metadatas"]]
    assert "changed" in names


def test_update_codebase_skips_unchanged(tmp_path):
    client = init_client(str(tmp_path / "chroma"))
    collection = get_collection(client, "test_update_skip")

    py_file = tmp_path / "stable.py"
    py_file.write_text(
        "def stable():\n"
        "    a = 1\n"
        "    return a\n"
    )
    from code_index.chunker import split_python_code
    update_codebase(str(tmp_path), collection, split_python_code)
    count_before = collection.count()

    update_codebase(str(tmp_path), collection, split_python_code)
    count_after = collection.count()

    assert count_before == count_after
