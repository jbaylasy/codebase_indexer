import os
import json
import time
import threading
from datetime import datetime, timezone


_log_lock = threading.Lock()
_log_file = None


def init_audit_log(log_dir=None):
    global _log_file
    if log_dir is None:
        log_dir = os.getenv("CODE_INDEX_AUDIT_DIR")
    if log_dir is None:
        return
    os.makedirs(log_dir, exist_ok=True)
    _log_file = os.path.join(log_dir, f"audit_{datetime.now().strftime('%Y%m%d')}.jsonl")
    _write_entry({"event": "audit_initialized", "log_file": _log_file})


def _write_entry(entry):
    if _log_file is None:
        return
    entry["timestamp"] = datetime.now(timezone.utc).isoformat()
    with _log_lock:
        try:
            with open(_log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass


def log_search(query, codebase_name, n_results, result_count):
    _write_entry({
        "event": "search",
        "query_length": len(query) if query else 0,
        "codebase": codebase_name,
        "n_requested": n_results,
        "n_returned": result_count,
    })


def log_list_codebases(table_count):
    _write_entry({
        "event": "list_codebases",
        "table_count": table_count,
    })


def log_remove_codebase(codebase_name, success):
    _write_entry({
        "event": "remove_codebase",
        "codebase": codebase_name,
        "success": success,
    })


def log_index(codebase_name, chunk_count):
    _write_entry({
        "event": "index",
        "codebase": codebase_name,
        "chunk_count": chunk_count,
    })


def log_watcher_event(file_path, event_type, codebase_name):
    _write_entry({
        "event": "watcher_update",
        "file": os.path.basename(file_path),
        "change_type": event_type,
        "codebase": codebase_name,
    })


def log_security_event(event_type, details=None):
    entry = {"event": "security", "security_event": event_type}
    if details:
        entry["details"] = details
    _write_entry(entry)


def log_error(context, error_type):
    _write_entry({
        "event": "error",
        "context": context,
        "error_type": error_type,
    })
