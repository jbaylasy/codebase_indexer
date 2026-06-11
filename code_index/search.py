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


def _rrf_merge(vector_results, fts_results, k=60):
    scores = {}
    docs = {}
    for rank, r in enumerate(vector_results):
        key = (r.get("file", ""), r.get("start_line", 0), r.get("name", ""))
        scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
        docs[key] = r
    for rank, r in enumerate(fts_results):
        key = (r.get("file", ""), r.get("start_line", 0), r.get("name", ""))
        scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
        docs[key] = r
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [docs[key] for key, _ in ranked]


def search_code_hybrid(query, table, n_results=3):
    from code_index.embedder import embed_query
    embedding = embed_query(query)
    candidates = n_results * 3
    vector_results = []
    raw_vector = table.search(embedding.tolist()).limit(candidates).to_list()
    for r in raw_vector:
        vector_results.append({
            "file": r.get("file", ""),
            "start_line": r.get("start_line", 0),
            "name": r.get("name", ""),
            "type": r.get("type", ""),
            "distance": r.get("_distance", 0.0),
            "code": r.get("text", ""),
        })
    fts_results = []
    try:
        raw_fts = table.search(query, query_type="fts").limit(candidates).to_list()
        for r in raw_fts:
            fts_results.append({
                "file": r.get("file", ""),
                "start_line": r.get("start_line", 0),
                "name": r.get("name", ""),
                "type": r.get("type", ""),
                "distance": r.get("_distance", 0.0),
                "code": r.get("text", ""),
            })
    except Exception:
        pass
    merged = _rrf_merge(vector_results, fts_results)
    results = merged[:n_results]
    return {
        "query": query,
        "results": results,
        "raw": raw_vector,
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
