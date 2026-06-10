from collections import OrderedDict
from sentence_transformers import SentenceTransformer
from code_index.config import EMBEDDING_MODEL

_model = None
_cache = None
_cache_size = 512


def init_embedder(cache_size=512, model_name=None):
    global _model, _cache, _cache_size
    if _model is None:
        name = model_name or EMBEDDING_MODEL
        _model = SentenceTransformer(name)
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
    return _model.encode(texts, normalize_embeddings=True, show_progress_bar=False)


def warm_up():
    init_embedder()
    embed_query("__warmup__")
    _cache.clear()
