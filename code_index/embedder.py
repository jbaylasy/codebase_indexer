import os
import hashlib
import json
import warnings
import logging
from collections import OrderedDict

logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", message=".*unauthenticated requests.*")
warnings.filterwarnings("ignore", message=".*HF_TOKEN.*")

_LOCAL_MODEL_DIR = os.path.join(os.path.expanduser("~"), ".cache", "code_index_models")
os.makedirs(_LOCAL_MODEL_DIR, exist_ok=True)
os.environ.setdefault("TRANSFORMERS_CACHE", _LOCAL_MODEL_DIR)
os.environ.setdefault("HF_HOME", _LOCAL_MODEL_DIR)
os.environ.setdefault("HF_HUB_CACHE", _LOCAL_MODEL_DIR)

from sentence_transformers import SentenceTransformer
from code_index.config import EMBEDDING_MODEL, EMBEDDING_MODEL_SHA256, EMBEDDING_OFFLINE, EMBEDDING_BATCH_SIZE

_model = None
_cache = None
_cache_size = 512


def _verify_model_hash(model):
    if not EMBEDDING_MODEL_SHA256:
        return True
    model_dir = model[0].folder if hasattr(model, '__iter__') else None
    if model_dir is None:
        try:
            model_dir = model._model_card if hasattr(model, '_model_card') else None
        except Exception:
            pass
    if model_dir is None:
        try:
            if hasattr(model, '_first_module'):
                model_dir = model._first_module().folder
            elif hasattr(model, 'folder'):
                model_dir = model.folder
        except Exception:
            pass
    if model_dir is None:
        print("Warning: Could not verify model hash - model directory not found")
        return True

    h = hashlib.sha256()
    for root, dirs, files in os.walk(model_dir):
        dirs.sort()
        for fn in sorted(files):
            fp = os.path.join(root, fn)
            if fn.endswith(('.json', '.txt', '.model', '.bin', '.safetensors')):
                with open(fp, 'rb') as f:
                    for chunk in iter(lambda: f.read(8192), b''):
                        h.update(chunk)
    computed = h.hexdigest()
    if computed != EMBEDDING_MODEL_SHA256:
        raise ValueError(
            f"Model hash mismatch! Expected {EMBEDDING_MODEL_SHA256}, got {computed}"
        )
    return True


def init_embedder(cache_size=512, model_name=None):
    global _model, _cache, _cache_size
    if _model is None:
        name = model_name or EMBEDDING_MODEL
        kwargs = {"cache_folder": _LOCAL_MODEL_DIR}
        if EMBEDDING_OFFLINE:
            kwargs["cache_folder"] = os.environ.get(
                "TRANSFORMERS_CACHE",
                _LOCAL_MODEL_DIR,
            )
        _model = SentenceTransformer(name, **kwargs)
        _verify_model_hash(_model)
    _cache_size = cache_size
    _cache = OrderedDict()


def embed_query(query):
    global _cache
    if _cache is None:
        init_embedder()
    if query in _cache:
        _cache.move_to_end(query)
        return _cache[query]
    embedding = _model.encode(query, normalize_embeddings=True)
    _cache[query] = embedding
    if len(_cache) > _cache_size:
        _cache.popitem(last=False)
    return embedding


def embed_documents(texts):
    global _model
    if _model is None:
        init_embedder()
    return _model.encode(texts, normalize_embeddings=True, show_progress_bar=True, batch_size=EMBEDDING_BATCH_SIZE)


def warm_up():
    init_embedder()
    embed_query("__warmup__")
    _cache.clear()
