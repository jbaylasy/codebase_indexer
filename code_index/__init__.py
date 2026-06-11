from code_index.chunker import split_python_code, split_js_ts_code, get_file_paths
from code_index.database import init_client, get_collection, index_codebase, update_codebase
from code_index.search import search_code, format_results
from code_index.parser import parse_questions
from code_index.exporter import export_results
from code_index.secret_scanner import scan_and_redact, redact_chunk
from code_index.path_security import validate_root_dir, is_safe_path
from code_index.encryption import encrypt_lance_db, decrypt_lance_db
from code_index.config_loader import load_config, get_codebases_from_config, find_config_file
from code_index.config_setup import run_setup, find_git_root
from code_index.audit import init_audit_log, log_search, log_list_codebases, log_remove_codebase
