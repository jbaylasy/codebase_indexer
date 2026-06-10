import os
import hashlib
import uuid
import chromadb


def init_client(db_path="./code_index_db"):
    """Initialize a persistent ChromaDB client.

    Args:
        db_path: Path to the ChromaDB persistence directory.

    Returns:
        A chromadb.PersistentClient instance.
    """
    return chromadb.PersistentClient(path=db_path)


def get_collection(client, name):
    """Get or create a named ChromaDB collection.

    Args:
        client: A chromadb.Client instance.
        name: The collection name.

    Returns:
        A chromadb.Collection instance.
    """
    return client.get_or_create_collection(name=name)


def _hash_file(file_path):
    """Compute the MD5 hash of a file's contents.

    Args:
        file_path: Absolute path to the file.

    Returns:
        Hex digest string of the MD5 hash.
    """
    with open(file_path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


def index_codebase(chunks, collection):
    """Add chunk data to a ChromaDB collection.

    Each chunk's metadata is augmented with a 'file_hash' field derived from
    the source file's MD5 digest for incremental update support.

    Args:
        chunks: A list of dicts with 'text' and 'metadata' keys.
        collection: A ChromaDB collection to insert into.
    """
    if not chunks:
        return

    documents = [c["text"] for c in chunks]
    metadatas = []
    for c in chunks:
        meta = dict(c["metadata"])
        file_path = meta.get("file", "")
        if file_path and os.path.exists(file_path):
            meta["file_hash"] = _hash_file(file_path)
        else:
            meta["file_hash"] = ""
        metadatas.append(meta)
    ids = [str(uuid.uuid4()) for _ in range(len(chunks))]

    collection.add(
        documents=documents,
        metadatas=metadatas,
        ids=ids,
    )
    print(f"Added {len(documents)} chunks to the database.")


def update_codebase(root_dir, collection, chunker_fn):
    """Incrementally update a ChromaDB collection by re-indexing only changed files.

    Walks the directory, hashes each file, compares against stored hashes in
    ChromaDB metadata, and only re-chunks files whose hash has changed. Old
    chunks for changed files are deleted before new ones are added.

    Args:
        root_dir: The root directory to scan for source files.
        collection: A ChromaDB collection to update.
        chunker_fn: A callable(root_dir) that returns a list of chunk dicts.
    """
    current_file_hashes = {}
    for root, dirs, files in os.walk(root_dir):
        for d in dirs[:]:
            if d.startswith("."):
                dirs.remove(d)
        for file in files:
            full_path = os.path.join(root, file)
            current_file_hashes[full_path] = _hash_file(full_path)

    stored_hashes = {}
    if collection.count() > 0:
        all_meta = collection.get(include=["metadatas"])
        for meta in all_meta["metadatas"]:
            fp = meta.get("file", "")
            fh = meta.get("file_hash", "")
            if fp:
                stored_hashes[fp] = fh

    changed_files = []
    new_files = []
    for fp, fh in current_file_hashes.items():
        if fp not in stored_hashes:
            new_files.append(fp)
        elif stored_hashes[fp] != fh:
            changed_files.append(fp)

    unchanged_skipped = len(current_file_hashes) - len(changed_files) - len(new_files)

    if not changed_files and not new_files:
        print(f"No changes detected ({unchanged_skipped} files unchanged).")
        return

    files_to_reindex = changed_files + new_files

    if changed_files:
        for fp in changed_files:
            try:
                collection.delete(where={"file": fp})
            except Exception:
                pass
        print(f"Deleted old chunks for {len(changed_files)} changed files.")

    new_chunks = []
    for fp in files_to_reindex:
        with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        chunks = chunker_fn(content, fp)
        new_chunks.extend(chunks)

    if new_chunks:
        existing_count = collection.count()
        documents = [c["text"] for c in new_chunks]
        metadatas = []
        for c in new_chunks:
            meta = dict(c["metadata"])
            meta["file_hash"] = current_file_hashes.get(meta.get("file", ""), "")
            metadatas.append(meta)
        ids = [str(uuid.uuid4()) for _ in range(len(new_chunks))]

        collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids,
        )
        print(f"Indexed {len(new_chunks)} chunks from {len(files_to_reindex)} files "
              f"({len(new_files)} new, {len(changed_files)} changed, {unchanged_skipped} unchanged).")
    else:
        print(f"No chunks extracted from {len(files_to_reindex)} changed/new files.")
