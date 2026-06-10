import re

STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "must", "shall", "can", "need", "dare",
    "to", "of", "in", "for", "on", "with", "at", "by", "from", "as",
    "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "further", "then",
    "once", "here", "there", "when", "where", "why", "how", "all", "each",
    "every", "both", "few", "more", "most", "other", "some", "such", "no",
    "not", "only", "own", "same", "so", "than", "too", "very", "just",
    "because", "but", "and", "or", "if", "while", "about", "up", "its",
    "it", "this", "that", "these", "those", "i", "me", "my", "myself",
    "we", "our", "ours", "you", "your", "he", "him", "his", "she", "her",
    "they", "them", "their", "what", "which", "who", "whom",
}


def _extract_keywords(query):
    words = re.findall(r'\b\w+\b', query.lower())
    return [w for w in words if w not in STOP_WORDS and len(w) > 1]


def _keyword_overlap_score(keywords, text, file_path, name):
    combined = f"{text} {file_path} {name}".lower()
    if not keywords:
        return 0.0
    hits = sum(1 for kw in keywords if kw in combined)
    return hits / len(keywords)


def search_code(query, collection, n_results=3, hybrid=True):
    """Search the indexed codebase for chunks matching a natural language query.

    Args:
        query: A natural language question or search term.
        collection: The ChromaDB collection to query against.
        n_results: Number of top results to return.
        hybrid: If True, use hybrid search combining semantic and keyword scoring.

    Returns:
        A dict with 'query', 'results' (list of result dicts), and 'raw' (ChromaDB response).
    """
    if hybrid:
        return search_code_hybrid(query, collection, n_results)

    from code_index.embedder import embed_query
    embedding = embed_query(query)
    raw = collection.query(
        query_embeddings=[embedding.tolist()],
        n_results=n_results,
    )

    results = []
    for i in range(min(n_results, len(raw["metadatas"][0]))):
        results.append({
            "file": raw["metadatas"][0][i].get("file", ""),
            "start_line": raw["metadatas"][0][i].get("start_line", 0),
            "name": raw["metadatas"][0][i].get("name", ""),
            "type": raw["metadatas"][0][i].get("type", ""),
            "distance": raw["distances"][0][i],
            "code": raw["documents"][0][i],
        })

    return {
        "query": query,
        "results": results,
        "raw": raw,
    }


def search_code_hybrid(query, collection, n_results=3):
    """Hybrid search combining semantic vector search with keyword overlap scoring.

    Retrieves n_results * 3 candidates via semantic search, then re-ranks using
    a combined score of 0.7 * semantic_score + 0.3 * keyword_overlap_score.

    Args:
        query: A natural language question or search term.
        collection: The ChromaDB collection to query against.
        n_results: Number of top results to return.

    Returns:
        A dict with 'query', 'results' (list of result dicts), and 'raw' (ChromaDB response).
    """
    from code_index.embedder import embed_query
    embedding = embed_query(query)
    candidates = n_results * 3
    raw = collection.query(
        query_embeddings=[embedding.tolist()],
        n_results=candidates,
    )

    keywords = _extract_keywords(query)

    scored = []
    for i in range(min(candidates, len(raw["metadatas"][0]))):
        distance = raw["distances"][0][i]
        semantic_score = 1.0 / (1.0 + distance)

        doc_text = raw["documents"][0][i]
        file_path = raw["metadatas"][0][i].get("file", "")
        name = raw["metadatas"][0][i].get("name", "")
        kw_score = _keyword_overlap_score(keywords, doc_text, file_path, name)

        combined = 0.7 * semantic_score + 0.3 * kw_score

        scored.append({
            "combined": combined,
            "result": {
                "file": file_path,
                "start_line": raw["metadatas"][0][i].get("start_line", 0),
                "name": name,
                "type": raw["metadatas"][0][i].get("type", ""),
                "distance": distance,
                "code": doc_text,
            },
        })

    scored.sort(key=lambda x: x["combined"], reverse=True)
    results = [s["result"] for s in scored[:n_results]]

    return {
        "query": query,
        "results": results,
        "raw": raw,
    }


def format_results(search_output, n_results=None):
    """Format search results into a human-readable string.

    Args:
        search_output: The dict returned by search_code().
        n_results: Number of results to display (defaults to all).

    Returns:
        A formatted string representation of the search results.
    """
    query = search_output["query"]
    results = search_output["results"]
    if n_results is not None:
        results = results[:n_results]

    lines = [f'\nQuery: "{query}"', "=" * 60]
    for i, r in enumerate(results):
        lines.append(f"--- Result {i + 1} ---")
        lines.append(f"File:   {r['file']}")
        lines.append(f"Line:   {r['start_line']}")
        lines.append(f"Name:   {r['name']}")
        lines.append(f"Type:   {r['type']}")
        lines.append(f"Score:  {r['distance']:.4f}")
        lines.append(f"Code:\n{r['code']}")
        lines.append("-" * 60)

    return "\n".join(lines)
