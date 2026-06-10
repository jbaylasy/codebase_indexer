import os


def export_results(query, results, codebase_name, n_results=3):
    """Write search results to a per-codebase markdown file in results/.

    Accepts either the structured dict returned by search_code() or the raw
    ChromaDB query results dict for backward compatibility.

    Args:
        query: The search query string.
        results: The search results dict (structured or raw ChromaDB format).
        codebase_name: Name of the codebase for the output file.
        n_results: Number of results included.
    """
    os.makedirs("results", exist_ok=True)
    filepath = os.path.join("results", f"{codebase_name}_results.md")

    formatted_results = _normalize_results(results)

    with open(filepath, "a") as f:
        f.write(f"\n## Q: {query}\n\n")
        for i, r in enumerate(formatted_results[:n_results]):
            f.write(f"### Result {i + 1}\n")
            f.write(f"- **File:** {r['file']}\n")
            f.write(f"- **Line:** {r['start_line']}\n")
            f.write(f"- **Name:** {r['name']}\n")
            f.write(f"- **Score:** {r['distance']:.4f}\n\n")
            f.write(f"```{r.get('type', '')}\n{r['code']}\n```\n\n")

    print(f"Appended to {filepath}")


def _normalize_results(results):
    """Normalize results from either structured dict or raw ChromaDB format.

    Args:
        results: A search_code() output dict or raw ChromaDB results dict.

    Returns:
        A list of result dicts with 'file', 'start_line', 'name', 'distance', 'code', 'type' keys.
    """
    if "results" in results and isinstance(results["results"], list):
        return results["results"]

    items = []
    if "metadatas" in results and results["metadatas"]:
        for i in range(len(results["metadatas"][0])):
            meta = results["metadatas"][0][i]
            items.append({
                "file": meta.get("file", ""),
                "start_line": meta.get("start_line", 0),
                "name": meta.get("name", ""),
                "type": meta.get("type", ""),
                "distance": results["distances"][0][i],
                "code": results["documents"][0][i],
            })
    return items
