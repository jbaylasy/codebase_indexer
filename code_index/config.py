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
