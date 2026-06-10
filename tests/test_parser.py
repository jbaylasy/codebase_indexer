import tempfile
import os
from code_index.parser import parse_questions


def _write_temp(content):
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False)
    f.write(content)
    f.close()
    return f.name


def test_parse_questions_extracts_questions():
    content = (
        "# Card Shop\n"
        "1. How does the card shop work?\n"
        "2. What pricing model is used?\n"
    )
    path = _write_temp(content)
    try:
        result = parse_questions(path)
        assert "card_shop" in result
        assert len(result["card_shop"]) == 2
        assert "How does the card shop work?" in result["card_shop"]
    finally:
        os.unlink(path)


def test_parse_questions_infrastructure_maps():
    content = (
        "# Infrastructure\n"
        "1. How is the system deployed?\n"
        "2. What monitoring tools are used?\n"
    )
    path = _write_temp(content)
    try:
        result = parse_questions(path)
        assert "card_infrastructure" in result
        assert len(result["card_infrastructure"]) == 2
    finally:
        os.unlink(path)


def test_parse_questions_multiple_sections():
    content = (
        "# Card Shop\n"
        "1. How does purchasing work?\n"
        "\n"
        "# Card Collection\n"
        "1. How are cards organized?\n"
        "2. What filters exist?\n"
        "\n"
        "# Infrastructure\n"
        "1. How is deployment done?\n"
    )
    path = _write_temp(content)
    try:
        result = parse_questions(path)
        assert "card_shop" in result
        assert "card_collection" in result
        assert "card_infrastructure" in result
        assert len(result["card_shop"]) == 1
        assert len(result["card_collection"]) == 2
        assert len(result["card_infrastructure"]) == 1
    finally:
        os.unlink(path)
