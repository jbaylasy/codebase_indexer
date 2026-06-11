import os
import time
import hashlib
import threading

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from code_index.chunker import split_with_treesitter, _CODE_EXTENSIONS
from code_index.database import get_collection, update_codebase
from code_index.embedder import embed_documents
from code_index.secret_scanner import redact_chunk
from code_index.path_security import is_safe_path
from code_index.config import PERIODIC_REINDEX_SECONDS

ALLOWED_EXTENSIONS = _CODE_EXTENSIONS
DEBOUNCE_SECONDS = 2


def _chunk_file(file_path):
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except (OSError, IOError):
        return []
    return split_with_treesitter(content, file_path)


def _delete_chunks_for_file(table, file_path):
    try:
        arrow_table = table.to_arrow()
        files = arrow_table.column("file").to_pylist()
        count = sum(1 for f in files if f == file_path)
        if count > 0:
            table.delete(f'file = "{file_path}"')
            return count
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


class _DebouncingHandler(FileSystemEventHandler):
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

        table = cb["table"]

        if event_type == "deleted":
            removed = _delete_chunks_for_file(table, file_path)
            if removed:
                print(f"[watcher] [{cb['name']}] Deleted {removed} chunks: {file_path}")
                self._processed += removed
            return

        if not os.path.exists(file_path):
            return

        if os.path.islink(file_path):
            if not is_safe_path(file_path, cb["root"]):
                return

        removed = _delete_chunks_for_file(table, file_path)
        raw_chunks = _chunk_file(file_path)
        chunks = [redact_chunk(c) for c in raw_chunks]

        if not chunks:
            return

        try:
            texts = [c["text"] for c in chunks]
            vectors = embed_documents(texts).tolist()
            records = []
            for i, c in enumerate(chunks):
                meta = dict(c["metadata"])
                try:
                    with open(file_path, "rb") as fh:
                        meta["file_hash"] = hashlib.md5(fh.read()).hexdigest()
                except Exception:
                    meta["file_hash"] = ""
                records.append({
                    "vector": vectors[i],
                    "text": texts[i],
                    "file": meta.get("file", ""),
                    "start_line": meta.get("start_line", 1),
                    "type": meta.get("type", "file"),
                    "name": meta.get("name", ""),
                    "file_hash": meta.get("file_hash", ""),
                })
            table.add(records)
            action = "Updated" if removed else "Indexed"
            print(f"[watcher] [{cb['name']}] {action} {len(chunks)} chunks: {file_path}")
            self._processed += len(chunks)
        except Exception as e:
            print(f"[watcher] [{cb['name']}] Error: {file_path}: {e}")


def start_watcher(codebases):
    handler = _DebouncingHandler(codebases)
    observer = Observer()

    seen_roots = set()
    for cb in codebases:
        real_root = os.path.realpath(cb["root"])
        if real_root not in seen_roots:
            observer.schedule(handler, cb["root"], recursive=True)
            seen_roots.add(real_root)
            print(f"[watcher] Watching: {cb['root']} (as '{cb['name']}')")

    observer.daemon = True
    observer.start()
    return observer


def start_periodic_reindex(codebases, db_path, interval_seconds=None):
    interval = interval_seconds if interval_seconds is not None else PERIODIC_REINDEX_SECONDS
    if interval <= 0:
        return None

    def _reindex_loop():
        while True:
            time.sleep(interval)
            for cb in codebases:
                try:
                    table = cb["table"]
                    root = cb["root"]
                    name = cb["name"]
                    update_codebase(root, table, split_with_treesitter, db_path=db_path, codebase_name=name)
                except Exception as e:
                    print(f"[reindex] [{name}] Error: {e}")

    thread = threading.Thread(target=_reindex_loop, daemon=True, name="periodic-reindex")
    thread.start()
    print(f"[reindex] Periodic re-index every {interval}s")
    return thread
