import os
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("CODE_INDEX_DB_PATH", "./code_index_db")
DEFAULT_N_RESULTS = int(os.getenv("CODE_INDEX_N_RESULTS", "3"))
ALLOWED_EXTENSIONS = os.getenv(
    "CODE_INDEX_EXTENSIONS",
    ".py,.js,.jsx,.ts,.tsx,.md,.txt,.json,.sql",
).split(",")
DEBOUNCE_SECONDS = float(os.getenv("CODE_INDEX_DEBOUNCE", "2"))
EMBEDDING_CACHE_SIZE = int(os.getenv("CODE_INDEX_EMBEDDING_CACHE_SIZE", "512"))
EMBEDDING_BATCH_SIZE = int(os.getenv("CODE_INDEX_EMBEDDING_BATCH_SIZE", "256"))
EMBEDDING_MODEL = os.getenv("CODE_INDEX_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
EMBEDDING_MODEL_SHA256 = os.getenv("CODE_INDEX_EMBEDDING_MODEL_SHA256", "")
EMBEDDING_OFFLINE = os.getenv("CODE_INDEX_EMBEDDING_OFFLINE", "false").lower() in ("true", "1", "yes")
ALLOWED_BASE_DIRS = [d.strip() for d in os.getenv("CODE_INDEX_ALLOWED_DIRS", "").split(",") if d.strip()]
MAX_FILE_SIZE_MB = int(os.getenv("CODE_INDEX_MAX_FILE_SIZE_MB", "10"))
CHUNK_MAX_TOKENS = int(os.getenv("CODE_INDEX_CHUNK_MAX_TOKENS", "220"))
CHUNK_MIN_TOKENS = int(os.getenv("CODE_INDEX_CHUNK_MIN_TOKENS", "10"))
CHARS_PER_TOKEN = int(os.getenv("CODE_INDEX_CHARS_PER_TOKEN", "4"))
PERIODIC_REINDEX_SECONDS = int(os.getenv("CODE_INDEX_PERIODIC_REINDEX_SECONDS", "300"))
CODE_INDEX_API_KEY = os.getenv("CODE_INDEX_API_KEY", "")
