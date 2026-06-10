from collections import OrderedDict
from chromadb.utils import embedding_functions

_ef = None
_cache = None
_cache_size = 512


def init_embedder(cache_size=512):
    global _ef, _cache, _cache_size
    if _ef is None:
        _ef = embedding_functions.DefaultEmbeddingFunction()
    _cache_size = cache_size
    _cache = OrderedDict()


def embed_query(query):
    global _cache
    if _cache is None:
        init_embedder()
    if query in _cache:
        _cache.move_to_end(query)
        return _cache[query]
    embedding = _ef([query])[0]
    _cache[query] = embedding
    if len(_cache) > _cache_size:
        _cache.popitem(last=False)
    return embedding


def warm_up():
    init_embedder()
    embed_query("__warmup__")
    _cache.clear()
