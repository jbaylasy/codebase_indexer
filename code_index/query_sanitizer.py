import re


MAX_QUERY_LENGTH = 500
ALLOWED_TABLE_NAME_RE = re.compile(r'^[a-zA-Z0-9_-]+$')


def sanitize_query(query):
    if not query or not isinstance(query, str):
        raise ValueError("Query must be a non-empty string")
    query = query.strip()
    if not query:
        raise ValueError("Query must be a non-empty string")
    if len(query) > MAX_QUERY_LENGTH:
        raise ValueError(f"Query exceeds maximum length of {MAX_QUERY_LENGTH} characters")
    sanitized = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', query)
    return sanitized


def validate_codebase_name(name):
    if not name or not isinstance(name, str):
        raise ValueError("Codebase name must be a non-empty string")
    name = name.strip()
    if not name:
        raise ValueError("Codebase name must be a non-empty string")
    if len(name) > 128:
        raise ValueError("Codebase name exceeds maximum length of 128 characters")
    if not ALLOWED_TABLE_NAME_RE.match(name):
        raise ValueError("Codebase name contains invalid characters. Only alphanumeric, hyphens, and underscores allowed")
    return name


def validate_n_results(n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        raise ValueError("n_results must be an integer")
    if n < 1:
        raise ValueError("n_results must be at least 1")
    if n > 50:
        raise ValueError("n_results must be at most 50")
    return n
