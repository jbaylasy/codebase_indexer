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


def search_code(query, table, n_results=3, hybrid=True):
    if hybrid:
        return search_code_hybrid(query, table, n_results)
    from code_index.embedder import embed_query
    embedding = embed_query(query)
    raw_results = table.search(embedding.tolist()).limit(n_results).to_list()
    results = []
    for r in raw_results:
        results.append({
            "file": r.get("file", ""),
            "start_line": r.get("start_line", 0),
            "name": r.get("name", ""),
            "type": r.get("type", ""),
            "distance": r.get("_distance", 0.0),
            "code": r.get("text", ""),
        })
    return {
        "query": query,
        "results": results,
        "raw": raw_results,
    }


def search_code_hybrid(query, table, n_results=3):
    from code_index.embedder import embed_query
    embedding = embed_query(query)
    candidates = n_results * 3
    raw_results = table.search(embedding.tolist()).limit(candidates).to_list()
    keywords = _extract_keywords(query)
    scored = []
    for r in raw_results:
        distance = r.get("_distance", 0.0)
        semantic_score = 1.0 / (1.0 + distance)
        doc_text = r.get("text", "")
        file_path = r.get("file", "")
        name = r.get("name", "")
        kw_score = _keyword_overlap_score(keywords, doc_text, file_path, name)
        combined = 0.7 * semantic_score + 0.3 * kw_score
        scored.append({
            "combined": combined,
            "result": {
                "file": file_path,
                "start_line": r.get("start_line", 0),
                "name": name,
                "type": r.get("type", ""),
                "distance": distance,
                "code": doc_text,
            },
        })
    scored.sort(key=lambda x: x["combined"], reverse=True)
    results = [s["result"] for s in scored[:n_results]]
    return {
        "query": query,
        "results": results,
        "raw": raw_results,
    }


def format_results(search_output, n_results=None):
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
