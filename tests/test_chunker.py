import os
from code_index.chunker import split_python_code, split_js_ts_code, get_file_paths


def test_split_python_code_simple_function():
    source = (
        "def greet(name):\n"
        "    message = f'Hello {name}'\n"
        "    return message\n"
    )
    chunks = split_python_code(source, "example.py")
    assert len(chunks) == 1
    c = chunks[0]
    assert c["metadata"]["name"] == "greet"
    assert c["metadata"]["type"] == "function"
    assert c["metadata"]["file"] == "example.py"
    assert c["metadata"]["start_line"] == 1
    assert "def greet(name):" in c["text"]


def test_split_python_code_class():
    source = (
        "class MyClass:\n"
        "    def __init__(self):\n"
        "        self.value = 42\n"
        "\n"
        "    def get_value(self):\n"
        "        return self.value\n"
    )
    chunks = split_python_code(source, "cls.py")
    class_chunks = [c for c in chunks if c["metadata"]["type"] == "class"]
    assert len(class_chunks) >= 1
    assert class_chunks[0]["metadata"]["name"] == "MyClass"
    assert class_chunks[0]["metadata"]["type"] == "class"


def test_split_python_code_async_function():
    source = (
        "async def fetch_data(url):\n"
        "    import asyncio\n"
        "    await asyncio.sleep(1)\n"
        "    return url\n"
    )
    chunks = split_python_code(source, "async_mod.py")
    assert len(chunks) == 1
    assert chunks[0]["metadata"]["name"] == "fetch_data"
    assert chunks[0]["metadata"]["type"] == "function"
    assert "async def fetch_data" in chunks[0]["text"]


def test_split_python_code_filters_below_min_lines():
    source = (
        "def tiny():\n"
        "    pass\n"
    )
    chunks = split_python_code(source, "tiny.py", min_lines=3)
    assert len(chunks) == 0


def test_split_python_code_includes_docstring():
    source = (
        "def documented():\n"
        "    \"\"\"This does something.\"\"\"\n"
        "    x = 1\n"
        "    return x\n"
    )
    chunks = split_python_code(source, "doc.py")
    assert len(chunks) == 1
    assert '"""' in chunks[0]["text"]
    assert "This does something." in chunks[0]["text"]


def test_split_python_code_syntax_error():
    source = "def broken(:\n    pass\n"
    chunks = split_python_code(source, "broken.py")
    assert chunks == []


def test_split_js_ts_code_function_declaration():
    source = (
        "function add(a, b) {\n"
        "    const result = a + b;\n"
        "    return result;\n"
        "}\n"
    )
    chunks = split_js_ts_code(source, "math.js")
    assert len(chunks) >= 1
    assert any(c["metadata"]["name"] == "add" for c in chunks)


def test_split_js_ts_code_arrow_function():
    source = (
        "const multiply = (a, b) => {\n"
        "    const result = a * b;\n"
        "    return result;\n"
        "};\n"
    )
    chunks = split_js_ts_code(source, "arrow.js")
    assert len(chunks) >= 1
    assert any(c["metadata"]["name"] == "multiply" for c in chunks)


def test_split_js_ts_code_class():
    source = (
        "class Animal {\n"
        "    constructor(name) {\n"
        "        this.name = name;\n"
        "    }\n"
        "    speak() {\n"
        "        return this.name;\n"
        "    }\n"
        "}\n"
    )
    chunks = split_js_ts_code(source, "animal.js")
    assert any(c["metadata"]["name"] == "Animal" and c["metadata"]["type"] == "class" for c in chunks)


def test_get_file_paths(tmp_path):
    (tmp_path / "hello.py").write_text(
        "def hello():\n    print('hi')\n    return True\n"
    )
    (tmp_path / "notes.md").write_text("# Notes\nSome text here.\n")
    (tmp_path / "data.json").write_text('{"key": "value"}')

    chunks = get_file_paths(str(tmp_path))

    py_chunks = [c for c in chunks if c["metadata"]["file"].endswith("hello.py")]
    assert len(py_chunks) >= 1
    assert py_chunks[0]["metadata"]["type"] == "function"

    md_chunks = [c for c in chunks if c["metadata"]["file"].endswith("notes.md")]
    assert len(md_chunks) == 1
    assert md_chunks[0]["metadata"]["type"] == "file"

    json_chunks = [c for c in chunks if c["metadata"]["file"].endswith("data.json")]
    assert len(json_chunks) == 1


def test_split_js_ts_code_export_default_function():
    source = (
        "export default function App() {\n"
        "    return <div>Hello</div>;\n"
        "}\n"
    )
    chunks = split_js_ts_code(source, "App.tsx")
    assert any(c["metadata"]["name"] == "App" for c in chunks)


def test_split_js_ts_code_typescript_interface():
    source = (
        "interface Card {\n"
        "    name: string;\n"
        "    price: number;\n"
        "    rarity: string;\n"
        "}\n"
    )
    chunks = split_js_ts_code(source, "types.ts")
    assert any(c["metadata"]["name"] == "Card" and c["metadata"]["type"] == "interface" for c in chunks)


def test_split_js_ts_code_typescript_type():
    source = (
        "type PriceResult = {\n"
        "    low: number;\n"
        "    high: number;\n"
        "    average: number;\n"
        "};\n"
    )
    chunks = split_js_ts_code(source, "types.ts")
    assert any(c["metadata"]["name"] == "PriceResult" for c in chunks)


def test_split_js_ts_code_class_with_extends():
    source = (
        "class PremiumCard extends Card {\n"
        "    constructor(name) {\n"
        "        super(name);\n"
        "    }\n"
        "    getDiscount() {\n"
        "        return 0.1;\n"
        "    }\n"
        "}\n"
    )
    chunks = split_js_ts_code(source, "premium.js")
    assert any(c["metadata"]["name"] == "PremiumCard" and c["metadata"]["type"] == "class" for c in chunks)


def test_split_js_ts_code_export_async_function():
    source = (
        "export async function fetchData(url) {\n"
        "    const response = await fetch(url);\n"
        "    return response.json();\n"
        "}\n"
    )
    chunks = split_js_ts_code(source, "api.ts")
    assert any(c["metadata"]["name"] == "fetchData" for c in chunks)
