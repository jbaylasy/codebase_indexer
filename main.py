import os
from code_index.config import DB_PATH
from code_index import (
    init_client,
    get_collection,
    index_codebase,
    get_file_paths,
    search_code,
    format_results,
    parse_questions,
    export_results,
)


def main():
    codebases = {
        "card_shop": "test_codebase/card_shop",
        "card_collection": "test_codebase/card_collection",
        "card_infrastructure": "test_codebase/card_infrastructure",
        "financial_visuals": "test_codebase/financial_visuals",
    }

    client = init_client(DB_PATH)
    collections = {}

    for name, path in codebases.items():
        if not os.path.exists(path):
            print(f"Skipping {name} — directory not found: {path}")
            continue

        collection = get_collection(client, f"{name}_index")
        collections[name] = collection

        if collection.count() == 0:
            chunks = get_file_paths(path)
            print(f"\n[{name}] Found {len(chunks)} chunks in {path}")
            index_codebase(chunks, collection)
        else:
            print(f"\n[{name}] Already indexed, use watcher.py to update.")

    if os.path.exists("questions.md"):
        question_map = parse_questions("questions.md")
        print(f"\n=== Running {sum(len(v) for v in question_map.values())} Questions ===")

        for codebase_name, question_list in question_map.items():
            collection = collections.get(codebase_name)
            if not collection:
                print(f"\nSkipping {codebase_name} — not indexed.")
                continue

            filepath = os.path.join("results", f"{codebase_name}_results.md")
            os.makedirs("results", exist_ok=True)
            with open(filepath, "w") as f:
                f.write(f"# {codebase_name} — {len(question_list)} Questions\n")

            print(f"\n{'#' * 60}")
            print(f"# {codebase_name} — {len(question_list)} questions")
            print(f"{'#' * 60}")

            for q in question_list:
                output = search_code(q, collection)
                print(format_results(output))
                export_results(q, output, codebase_name)
    else:
        print("\nNo questions.md found. Running default queries.")
        for name, collection in collections.items():
            output = search_code(f"What are the main features of {name}?", collection)
            print(format_results(output))


if __name__ == "__main__":
    main()
