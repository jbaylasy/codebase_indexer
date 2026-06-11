import os
import hashlib
from code_index.database import init_client, get_collection, index_codebase, update_codebase


def test_init_client(tmp_path):
    client = init_client(str(tmp_path / "test_db"))
    assert hasattr(client, "open_table")
    assert hasattr(client, "table_names")


def test_get_collection(tmp_path):
    client = init_client(str(tmp_path / "test_db"))
    table = get_collection(client, "test_col")
    assert table.name == "test_col"


def test_index_codebase_adds_chunks_with_file_hash(tmp_path):
    py_file = tmp_path / "sample.py"
    py_file.write_text(
        "def greet(name):\n"
        "    msg = f'Hello {name}'\n"
        "    return msg\n"
    )
    client = init_client(str(tmp_path / "db"))
    table = get_collection(client, "test_idx")
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
    index_codebase(chunks, table, db_path=str(tmp_path / "db"), codebase_name="test_idx")
    assert table.count_rows() == 1
    arrow_table = table.to_arrow()
    file_hashes = arrow_table.column("file_hash").to_pylist()
    assert file_hashes[0] != ""


def test_update_codebase_detects_new_files(tmp_path):
    client = init_client(str(tmp_path / "db"))
    table = get_collection(client, "test_update_new")

    new_file = tmp_path / "new_module.py"
    new_file.write_text(
        "def compute(x):\n"
        "    y = x * 2\n"
        "    return y\n"
    )
    from code_index.chunker import split_python_code
    update_codebase(str(tmp_path), table, split_python_code, db_path=str(tmp_path / "db"), codebase_name="test_update_new")
    assert table.count_rows() >= 1


def test_update_codebase_detects_changed_files(tmp_path):
    src_path = str(tmp_path / "src")
    os.makedirs(src_path)
    db_path = str(tmp_path / "db")

    client = init_client(db_path)
    table = get_collection(client, "test_update_changed")

    py_file = tmp_path / "src" / "mod.py"
    py_file.write_text(
        "def original():\n"
        "    a = 1\n"
        "    b = a + 1\n"
        "    return b\n"
    )
    from code_index.chunker import split_python_code
    update_codebase(src_path, table, split_python_code, db_path=db_path, codebase_name="test_update_changed")
    assert table.count_rows() >= 1

    py_file.write_text(
        "def changed():\n"
        "    b = 2\n"
        "    c = b + 1\n"
        "    return c\n"
    )
    update_codebase(src_path, table, split_python_code, db_path=db_path, codebase_name="test_update_changed")

    arrow_table = table.to_arrow()
    names = arrow_table.column("name").to_pylist()
    assert "changed" in names


def test_update_codebase_skips_unchanged(tmp_path):
    db_path = str(tmp_path / "db")
    src_path = str(tmp_path / "src")
    os.makedirs(src_path)

    client = init_client(db_path)
    table = get_collection(client, "test_update_skip")

    py_file = tmp_path / "src" / "stable.py"
    py_file.write_text(
        "def stable():\n"
        "    a = 1\n"
        "    return a\n"
    )
    from code_index.chunker import split_python_code
    update_codebase(src_path, table, split_python_code, db_path=db_path, codebase_name="test_update_skip")
    count_before = table.count_rows()

    update_codebase(src_path, table, split_python_code, db_path=db_path, codebase_name="test_update_skip")
    count_after = table.count_rows()

    assert count_before == count_after
