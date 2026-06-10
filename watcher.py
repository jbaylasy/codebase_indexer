import os
import sys
import json
import uuid
import argparse
import threading
import time

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from code_index.chunker import split_python_code, split_js_ts_code, get_file_paths
from code_index.database import init_client, get_collection, index_codebase, update_codebase

ALLOWED_EXTENSIONS = (".py", ".js", ".jsx", ".ts", ".tsx", ".md", ".txt", ".json", ".sql")
DEBOUNCE_SECONDS = 2


def _chunk_file(file_path):
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except (OSError, IOError):
        return []

    if file_path.endswith(".py"):
        return split_python_code(content, file_path)
    elif file_path.endswith((".js", ".jsx", ".ts", ".tsx")):
        return split_js_ts_code(content, file_path)
    else:
        return [{
            "text": content,
            "metadata": {
                "file": file_path,
                "start_line": 1,
                "type": "file",
                "name": os.path.basename(file_path),
            },
        }]


def _delete_chunks_for_file(collection, file_path):
    try:
        existing = collection.get(where={"file": file_path})
        if existing["ids"]:
            collection.delete(where={"file": file_path})
            return len(existing["ids"])
    except Exception:
        pass
    return 0


def _find_codebase(file_path, codebases):
    resolved = os.path.realpath(file_path)
    for cb in codebases:
        root = os.path.realpath(cb["root"])
        if resolved.startswith(root + os.sep) or resolved == root:
            return cb
    return None


class DebouncingHandler(FileSystemEventHandler):
    def __init__(self, codebases):
        self.codebases = codebases
        self._pending = {}
        self._timer = None
        self._lock = threading.Lock()
        self._processed = 0

    def _is_allowed(self, path):
        if any(part.startswith(".") for part in path.split(os.sep)):
            return False
        return any(path.endswith(ext) for ext in ALLOWED_EXTENSIONS)

    def on_modified(self, event):
        if not event.is_directory and self._is_allowed(event.src_path):
            self._schedule(event.src_path, "modified")

    def on_created(self, event):
        if not event.is_directory and self._is_allowed(event.src_path):
            self._schedule(event.src_path, "created")

    def on_deleted(self, event):
        if not event.is_directory and self._is_allowed(event.src_path):
            self._schedule(event.src_path, "deleted")

    def on_moved(self, event):
        if not event.is_directory:
            if self._is_allowed(event.src_path):
                self._schedule(event.src_path, "deleted")
            if self._is_allowed(event.dest_path):
                self._schedule(event.dest_path, "created")

    def _schedule(self, file_path, event_type):
        with self._lock:
            self._pending[file_path] = event_type

            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(DEBOUNCE_SECONDS, self._process_pending)
            self._timer.daemon = True
            self._timer.start()

    def _process_pending(self):
        with self._lock:
            events = dict(self._pending)
            self._pending.clear()
            self._timer = None

        for file_path, event_type in events.items():
            self._handle_event(file_path, event_type)

    def _handle_event(self, file_path, event_type):
        cb = _find_codebase(file_path, self.codebases)
        if cb is None:
            return

        collection = cb["collection"]

        if event_type == "deleted":
            removed = _delete_chunks_for_file(collection, file_path)
            if removed:
                print(f"[{cb['name']}] Deleted {removed} chunks for deleted file: {file_path}")
                self._processed += removed
            return

        if not os.path.exists(file_path):
            return

        removed = _delete_chunks_for_file(collection, file_path)
        chunks = _chunk_file(file_path)

        if not chunks:
            return

        try:
            existing_count = collection.count()
            documents = [c["text"] for c in chunks]
            metadatas = []
            for c in chunks:
                meta = dict(c["metadata"])
                try:
                    with open(file_path, "rb") as fh:
                        import hashlib
                        meta["file_hash"] = hashlib.md5(fh.read()).hexdigest()
                except Exception:
                    meta["file_hash"] = ""
                metadatas.append(meta)
            ids = [str(uuid.uuid4()) for _ in range(len(chunks))]

            collection.add(documents=documents, metadatas=metadatas, ids=ids)
            action = "Updated" if removed else "Indexed"
            print(f"[{cb['name']}] {action} {len(chunks)} chunks from: {file_path}")
            self._processed += len(chunks)
        except Exception as e:
            print(f"[{cb['name']}] Error indexing {file_path}: {e}")


def _init_codebases(client, codebases):
    for cb in codebases:
        name = cb["name"]
        root = cb["root"]

        print(f"\nInitializing codebase '{name}' at {root}")
        collection = get_collection(client, name)
        cb["collection"] = collection

        if collection.count() == 0:
            print(f"  Collection '{name}' is empty. Running full index...")
            chunks = get_file_paths(root)
            if chunks:
                index_codebase(chunks, collection)
            else:
                print(f"  No files found to index in {root}")
        else:
            print(f"  Collection '{name}' has {collection.count()} chunks. Running incremental update...")
            update_codebase(root, collection, _chunk_file)


def main():
    parser = argparse.ArgumentParser(description="Background file watcher for code indexing")
    parser.add_argument("--db", default="./code_index_db", help="Path to ChromaDB directory")
    parser.add_argument("--watch", action="append", metavar="NAME=PATH",
                        help="Codebase to watch (format: name=/path/to/dir)")
    parser.add_argument("--config", help="Path to JSON config file")
    args = parser.parse_args()

    codebases = []

    if args.config:
        try:
            with open(args.config, "r") as f:
                config = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"Error reading config file: {e}")
            sys.exit(1)

        for entry in config.get("codebases", []):
            codebases.append({"name": entry["name"], "root": os.path.abspath(entry["root"])})
    elif args.watch:
        for item in args.watch:
            if "=" not in item:
                print(f"Invalid --watch format: '{item}'. Use name=path")
                sys.exit(1)
            name, path = item.split("=", 1)
            codebases.append({"name": name, "root": os.path.abspath(path)})
    else:
        parser.error("Must specify --config or at least one --watch")

    for cb in codebases:
        if not os.path.isdir(cb["root"]):
            print(f"Error: directory does not exist: {cb['root']}")
            sys.exit(1)

    print(f"Starting watcher with {len(codebases)} codebase(s)...")
    client = init_client(args.db)
    _init_codebases(client, codebases)

    handler = DebouncingHandler(codebases)
    observer = Observer()

    seen_roots = set()
    for cb in codebases:
        real_root = os.path.realpath(cb["root"])
        if real_root not in seen_roots:
            observer.schedule(handler, cb["root"], recursive=True)
            seen_roots.add(real_root)
            print(f"\nWatching: {cb['root']} (as '{cb['name']}')")

    observer.start()
    print("\nWatcher running. Press Ctrl+C to stop.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nStopping watcher...")
        observer.stop()
        print(f"Processed {handler._processed} chunk updates during this session.")

    observer.join()
    print("Watcher stopped.")


if __name__ == "__main__":
    main()
