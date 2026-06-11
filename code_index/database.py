import os
import json
import hashlib
import lancedb
import pyarrow as pa
from code_index.embedder import embed_documents


def init_client(db_path="./code_index_db"):
    return lancedb.connect(db_path)


def get_collection(db, name):
    try:
        return db.open_table(name)
    except Exception:
        schema = pa.schema([
            pa.field("vector", pa.list_(pa.float32(), 384)),
            pa.field("text", pa.string()),
            pa.field("file", pa.string()),
            pa.field("start_line", pa.int32()),
            pa.field("type", pa.string()),
            pa.field("name", pa.string()),
            pa.field("file_hash", pa.string()),
        ])
        empty = pa.table({
            "vector": pa.array([], type=pa.list_(pa.float32(), 384)),
            "text": pa.array([], type=pa.string()),
            "file": pa.array([], type=pa.string()),
            "start_line": pa.array([], type=pa.int32()),
            "type": pa.array([], type=pa.string()),
            "name": pa.array([], type=pa.string()),
            "file_hash": pa.array([], type=pa.string()),
        }, schema=schema)
        return db.create_table(name, empty)


def _hash_file(file_path):
    with open(file_path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


class MerkleTree:
    def __init__(self, root_dir):
        self.root_dir = root_dir
        self.file_hashes = {}
        self.dir_hashes = {}
        self._build(root_dir)

    def _build(self, directory):
        entries = []
        for entry in sorted(os.listdir(directory)):
            full = os.path.join(directory, entry)
            if entry.startswith("."):
                continue
            if os.path.isfile(full):
                h = _hash_file(full)
                self.file_hashes[full] = h
                entries.append(h)
            elif os.path.isdir(full):
                child_hash = self._build(full)
                entries.append(child_hash)
        combined = "".join(entries)
        dir_hash = hashlib.md5(combined.encode()).hexdigest()
        self.dir_hashes[directory] = dir_hash
        return dir_hash

    def get_changed_files(self, old_tree_state):
        if not old_tree_state:
            return list(self.file_hashes.keys()), []
        old_file_hashes = old_tree_state.get("file_hashes", {})
        old_dir_hashes = old_tree_state.get("dir_hashes", {})
        changed = []
        new = []
        if self.dir_hashes.get(self.root_dir) == old_dir_hashes.get(self.root_dir):
            return [], []
        for fp, fh in self.file_hashes.items():
            if fp not in old_file_hashes:
                new.append(fp)
            elif old_file_hashes[fp] != fh:
                changed.append(fp)
        return changed, new

    def to_state(self):
        return {"file_hashes": self.file_hashes, "dir_hashes": self.dir_hashes}


def _save_merkle_state(db_path, codebase_name, tree):
    state_file = os.path.join(db_path, f"merkle_{codebase_name}.json")
    os.makedirs(os.path.dirname(state_file), exist_ok=True)
    with open(state_file, "w") as f:
        json.dump(tree.to_state(), f)


def _load_merkle_state(db_path, codebase_name):
    state_file = os.path.join(db_path, f"merkle_{codebase_name}.json")
    if os.path.exists(state_file):
        with open(state_file, "r") as f:
            return json.load(f)
    return None


def index_codebase(chunks, table, db_path=None, codebase_name=None):
    if not chunks:
        return
    from code_index.embedder import embed_documents

    texts = [c["text"] for c in chunks]
    print(f"  Embedding {len(texts)} chunks...")
    vectors = embed_documents(texts).tolist()
    records = []
    for i, c in enumerate(chunks):
        meta = dict(c["metadata"])
        file_path = meta.get("file", "")
        if file_path and os.path.exists(file_path):
            fh = _hash_file(file_path)
        else:
            fh = ""
        records.append({
            "vector": vectors[i],
            "text": texts[i],
            "file": meta.get("file", ""),
            "start_line": meta.get("start_line", 1),
            "type": meta.get("type", "file"),
            "name": meta.get("name", ""),
            "file_hash": fh,
        })
    print(f"  Writing {len(records)} records to database...")
    table.add(records)
    _rebuild_fts_index(table)
    print(f"  Done — {len(records)} chunks indexed.")


def _rebuild_fts_index(table):
    try:
        table.create_fts_index("text", replace=True)
    except Exception:
        pass


def update_codebase(root_dir, table, chunker_fn, db_path=None, codebase_name=None):
    from code_index.embedder import embed_documents

    current_tree = MerkleTree(root_dir)
    old_state = _load_merkle_state(db_path or "./code_index_db", codebase_name or "unknown")
    changed_files, new_files = current_tree.get_changed_files(old_state)
    unchanged_skipped = len(current_tree.file_hashes) - len(changed_files) - len(new_files)

    if not changed_files and not new_files:
        print(f"  No changes detected ({unchanged_skipped} files unchanged).")
        return

    files_to_reindex = changed_files + new_files

    if changed_files:
        for fp in changed_files:
            try:
                table.delete(f'file = "{fp}"')
            except Exception:
                pass
        print(f"  Deleted old chunks for {len(changed_files)} changed files.")

    new_chunks = []
    for idx, fp in enumerate(files_to_reindex):
        print(f"    [{idx + 1}/{len(files_to_reindex)}] {os.path.basename(fp)}")
        with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        chunks = chunker_fn(content, fp)
        new_chunks.extend(chunks)

    if new_chunks:
        print(f"  Embedding {len(new_chunks)} chunks...")
        texts = [c["text"] for c in new_chunks]
        vectors = embed_documents(texts).tolist()
        records = []
        for i, c in enumerate(new_chunks):
            meta = dict(c["metadata"])
            records.append({
                "vector": vectors[i],
                "text": texts[i],
                "file": meta.get("file", ""),
                "start_line": meta.get("start_line", 1),
                "type": meta.get("type", "file"),
                "name": meta.get("name", ""),
                "file_hash": current_tree.file_hashes.get(meta.get("file", ""), ""),
            })
        print(f"  Writing {len(records)} records to database...")
        table.add(records)
        _rebuild_fts_index(table)
        print(f"  Done — {len(new_chunks)} chunks from {len(files_to_reindex)} files "
              f"({len(new_files)} new, {len(changed_files)} changed, {unchanged_skipped} unchanged).")

    _save_merkle_state(db_path or "./code_index_db", codebase_name or "unknown", current_tree)
