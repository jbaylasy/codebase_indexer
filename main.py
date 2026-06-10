import os
import argparse
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
    parser = argparse.ArgumentParser(description="Semantic code search - index and query codebases")
    parser.add_argument("--db", default=DB_PATH, help="Path to database directory")
    parser.add_argument("--index", action="append", metavar="NAME=PATH",
                        help="Codebase to index (format: name=/path/to/dir)")
    parser.add_argument("--questions", default="questions.md", help="Path to questions file")
    args = parser.parse_args()

    codebases = {}
    if args.index:
        for item in args.index:
            if "=" not in item:
                print(f"Invalid --index format: '{item}'. Use name=path")
                continue
            name, path = item.split("=", 1)
            codebases[name] = path

    db = init_client(args.db)
    tables = {}

    for name, path in codebases.items():
        if not os.path.exists(path):
            print(f"Skipping {name} — directory not found: {path}")
            continue

        table_name = f"{name}_index"
        table = get_collection(db, table_name)
        tables[name] = table

        if table.count_rows() == 0:
            chunks = get_file_paths(path)
            print(f"\n[{name}] Found {len(chunks)} chunks in {path}")
            index_codebase(chunks, table, db_path=args.db, codebase_name=name)
        else:
            print(f"\n[{name}] Already indexed ({table.count_rows()} chunks), use watcher.py to update.")

    if os.path.exists(args.questions):
        question_map = parse_questions(args.questions)
        print(f"\n=== Running {sum(len(v) for v in question_map.values())} Questions ===")

        for codebase_name, question_list in question_map.items():
            table_name = f"{codebase_name}_index"
            if table_name not in tables:
                try:
                    tables[codebase_name] = db.open_table(table_name)
                except Exception:
                    print(f"\nSkipping {codebase_name} — not indexed.")
                    continue

            table = tables[codebase_name]
            filepath = os.path.join("results", f"{codebase_name}_results.md")
            os.makedirs("results", exist_ok=True)
            with open(filepath, "w") as f:
                f.write(f"# {codebase_name} — {len(question_list)} Questions\n")

            print(f"\n{'#' * 60}")
            print(f"# {codebase_name} — {len(question_list)} questions")
            print(f"{'#' * 60}")

            for q in question_list:
                output = search_code(q, table)
                print(format_results(output))
                export_results(q, output, codebase_name)
    else:
        print(f"\nNo {args.questions} found. Running default queries.")
        for name, table in tables.items():
            output = search_code(f"What are the main features of {name}?", table)
            print(format_results(output))


if __name__ == "__main__":
    main()
