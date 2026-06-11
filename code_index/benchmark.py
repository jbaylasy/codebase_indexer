import os
import re
import json
import glob
import subprocess
import time
from datetime import datetime
from statistics import median

from code_index.database import init_client, get_collection
from code_index.search import search_code
from code_index.embedder import warm_up, init_embedder
from code_index.chunker import get_file_paths
from code_index.database import index_codebase

STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "as", "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "further", "then",
    "once", "and", "but", "or", "nor", "not", "so", "yet", "both", "either",
    "neither", "each", "every", "all", "any", "few", "more", "most", "other",
    "some", "such", "no", "only", "own", "same", "than", "too", "very",
    "just", "because", "if", "when", "where", "how", "what", "which", "who",
    "whom", "this", "that", "these", "those", "it", "its", "does", "do",
    "done", "many", "much", "about", "up", "there", "here", "he", "she",
    "they", "them", "we", "you", "i", "me", "my", "your", "his", "her",
}

SKIP_TARGETS = {
    "select", "from", "where", "insert", "update", "delete", "create",
    "drop", "alter", "table", "index", "join", "left", "right", "inner",
    "outer", "on", "and", "or", "not", "null", "true", "false", "set",
    "get", "post", "put", "patch", "delete", "head", "options", "api",
    "url", "http", "https", "json", "html", "css", "sql", "redis",
    "postgres", "sqlite", "docker", "python", "javascript", "react",
}

GREP_EXTENSIONS = [
    "*.py", "*.js", "*.jsx", "*.ts", "*.tsx", "*.rs", "*.go", "*.java",
    "*.c", "*.cpp", "*.cc", "*.cxx", "*.h", "*.hpp", "*.hxx",
    "*.md", "*.txt", "*.json", "*.sql", "*.yaml", "*.yml", "*.toml",
    "*.env", "*.cfg", "*.ini", "*.sh", "*.bash", "*.zsh", "*.fish",
    "*.html", "*.css", "*.scss", "*.less", "*.vue", "*.svelte",
    "*.dockerfile", "Dockerfile", "Makefile", "*.conf",
]

_ground_truth_cache = None


def _discover_codebases():
    from code_index.config_loader import get_codebases_from_config
    codebases = get_codebases_from_config()
    if codebases:
        return {cb["name"]: cb["root"] for cb in codebases}
    test_dir = "test_codebase"
    if os.path.isdir(test_dir):
        return {
            d: os.path.join(test_dir, d)
            for d in sorted(os.listdir(test_dir))
            if os.path.isdir(os.path.join(test_dir, d)) and not d.startswith(".")
        }
    return {}


def _load_questions(path="questions.md"):
    section_map = {
        "card shop": "card_shop",
        "card collection": "card_collection",
        "infrastructure": "card_infrastructure",
        "scripts": "card_infrastructure",
    }
    questions = {}
    current = None
    if not os.path.exists(path):
        return questions
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("# ") and not line.startswith("## "):
                name = re.sub(r'[^\w\s]', '', line.lstrip("# ")).strip().lower()
                for key, mapped in section_map.items():
                    if key in name:
                        current = mapped
                        if current not in questions:
                            questions[current] = []
                        break
                continue
            match = re.match(r'^\d+\.\s+(.+)', line)
            if match and current:
                questions[current].append(match.group(1))
    return questions

_ground_truth_cache = None


def _load_ground_truth(path="benchmark_ground_truth.json"):
    global _ground_truth_cache
    if _ground_truth_cache is not None:
        return _ground_truth_cache
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        data = json.load(f)
    _ground_truth_cache = {}
    for entry in data:
        key = entry["question"].strip()
        _ground_truth_cache[key] = entry
    return _ground_truth_cache


def _extract_targets(question):
    targets = re.findall(r'`([^`]+)`', question)
    gt = _load_ground_truth()
    entry = gt.get(question.strip())
    if entry:
        targets = targets or entry.get("expected_names", [])
        targets += entry.get("expected_keywords", [])
    targets = [t for t in targets if t.lower() not in SKIP_TARGETS and len(t) > 1]
    return list(set(targets))


def _extract_keywords(query):
    words = re.findall(r'\b\w+\b', query.lower())
    return [w for w in words if w not in STOP_WORDS and len(w) > 2][:3]


def _run_semantic(query, table, n=5):
    t0 = time.time()
    try:
        result = search_code(query, table, n_results=n)
        elapsed = (time.time() - t0) * 1000
        return result["results"], elapsed
    except Exception as e:
        return [], (time.time() - t0) * 1000


def _run_grep(keywords, codebase_dir, n=5):
    if not keywords:
        return [], 0.0
    t0 = time.time()
    try:
        ext_args = []
        for e in GREP_EXTENSIONS:
            ext_args.extend(["--include", e])
        cmd = ["grep", "-rn", "-l"] + ext_args + keywords[:1] + [codebase_dir]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        files = proc.stdout.strip().split("\n") if proc.stdout.strip() else []
        elapsed = (time.time() - t0) * 1000
        return [f.strip() for f in files[:n]], elapsed
    except Exception:
        return [], (time.time() - t0) * 1000


def _run_glob(keywords, codebase_dir, n=5):
    if not keywords:
        return [], 0.0
    t0 = time.time()
    try:
        files = set()
        for kw in keywords:
            pattern = os.path.join(codebase_dir, "**", f"*{kw}*")
            files.update(glob.glob(pattern, recursive=True))
        elapsed = (time.time() - t0) * 1000
        return sorted(files)[:n], elapsed
    except Exception:
        return [], (time.time() - t0) * 1000


def _check_match(results, targets, top_n):
    if not targets:
        return None
    for r in results[:top_n]:
        text = ""
        if isinstance(r, dict):
            text = f"{r.get('file', '')} {r.get('name', '')} {r.get('code', r.get('text', ''))}"
        elif isinstance(r, str):
            text = r
        for t in targets:
            if t.lower() in text.lower():
                return True
    return False


def _load_questions(path="questions.md"):
    codebase_map = {
        "card shop": "card_shop",
        "card collection": "card_collection",
        "infrastructure": "card_infrastructure",
        "scripts": "card_infrastructure",
    }
    questions = {}
    current = None
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("# ") and not line.startswith("## "):
                name = re.sub(r'[^\w\s]', '', line.lstrip("# ")).strip().lower()
                for key, mapped in codebase_map.items():
                    if key in name:
                        current = mapped
                        if current not in questions:
                            questions[current] = []
                        break
                continue
            match = re.match(r'^\d+\.\s+(.+)', line)
            if match and current:
                questions[current].append(match.group(1))
    return questions


def run_benchmark(db_path="./code_index_db"):
    print("Warming up embedder...")
    init_embedder()
    warm_up()

    db = init_client(db_path)

    print("Discovering codebases...")
    codebase_dirs = _discover_codebases()

    print("Loading questions...")
    all_questions = _load_questions()
    _load_ground_truth()

    results = []
    errors = []

    for cb_name, questions in all_questions.items():
        cb_dir = codebase_dirs.get(cb_name)
        if not cb_dir or not os.path.isdir(cb_dir):
            continue

        tbl_name = f"{cb_name}_index"
        table = get_collection(db, tbl_name)

        if table.count_rows() == 0:
            print(f"  Indexing {cb_name}...")
            chunks = get_file_paths(cb_dir)
            if chunks:
                index_codebase(chunks, table, db_path=db_path, codebase_name=cb_name)

        print(f"  Benchmarking {cb_name}: {len(questions)} questions")

        for i, question in enumerate(questions):
            targets = _extract_targets(question)
            keywords = _extract_keywords(question)

            sem_results, sem_time = _run_semantic(question, table)
            grep_files, grep_time = _run_grep(keywords, cb_dir)
            glob_files, glob_time = _run_glob(keywords, cb_dir)

            row = {
                "question": question,
                "codebase": cb_name,
                "targets": targets,
                "has_targets": bool(targets),
                "sem_top1": _check_match(sem_results, targets, 1),
                "sem_top3": _check_match(sem_results, targets, 3),
                "sem_top5": _check_match(sem_results, targets, 5),
                "grep_top1": _check_match(grep_files, targets, 1),
                "grep_top3": _check_match(grep_files, targets, 3),
                "grep_top5": _check_match(grep_files, targets, 5),
                "glob_top1": _check_match(glob_files, targets, 1),
                "glob_top3": _check_match(glob_files, targets, 3),
                "glob_top5": _check_match(glob_files, targets, 5),
                "sem_time": round(sem_time, 1),
                "grep_time": round(grep_time, 1),
                "glob_time": round(glob_time, 1),
            }
            results.append(row)

            if (i + 1) % 20 == 0:
                print(f"    {i + 1}/{len(questions)} done")

    return results, errors


def compute_stats(results):
    eligible = [r for r in results if r["has_targets"]]

    def _acc(key):
        hits = sum(1 for r in eligible if r[key] is True)
        return hits, len(eligible), round(100 * hits / len(eligible), 1) if eligible else 0

    def _timing(prefix):
        vals = [r[f"{prefix}_time"] for r in results if r[f"{prefix}_time"] > 0]
        if not vals:
            return {"avg": 0, "min": 0, "max": 0, "median": 0}
        return {
            "avg": round(sum(vals) / len(vals), 2),
            "min": round(min(vals), 2),
            "max": round(max(vals), 2),
            "median": round(median(vals), 2),
        }

    return {
        "total": len(results),
        "eligible": len(eligible),
        "accuracy": {
            "semantic": {"top1": _acc("sem_top1"), "top3": _acc("sem_top3"), "top5": _acc("sem_top5")},
            "grep": {"top1": _acc("grep_top1"), "top3": _acc("grep_top3"), "top5": _acc("grep_top5")},
            "glob": {"top1": _acc("glob_top1"), "top3": _acc("glob_top3"), "top5": _acc("glob_top5")},
        },
        "timing": {
            "semantic": _timing("sem"),
            "grep": _timing("grep"),
            "glob": _timing("glob"),
        },
    }


def print_summary(stats):
    print("\n" + "=" * 60)
    print("BENCHMARK RESULTS")
    print("=" * 60)
    print(f"Total questions: {stats['total']}")
    print(f"With extractable targets: {stats['eligible']}")

    print("\nAccuracy:")
    for method in ["semantic", "grep", "glob"]:
        print(f"\n  {method.upper()}:")
        for top in ["top1", "top3", "top5"]:
            hits, total, pct = stats["accuracy"][method][top]
            print(f"    {top}: {pct}% ({hits}/{total})")

    print("\nTiming (ms):")
    for method in ["semantic", "grep", "glob"]:
        t = stats["timing"][method]
        print(f"  {method}: avg={t['avg']}, min={t['min']}, max={t['max']}, median={t['median']}")


def export_markdown(results, stats, path="benchmark_results.md"):
    with open(path, "w") as f:
        f.write(f"# Benchmark Results: Semantic Search vs Grep vs Glob ({stats['total']} Questions)\n\n")
        f.write(f"_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_\n\n")

        f.write("## Summary\n\n")
        f.write(f"- **Total questions:** {stats['total']}\n")
        f.write(f"- **With extractable targets:** {stats['eligible']}\n\n")

        f.write("### Accuracy\n\n")
        f.write("| Metric | Semantic | Grep | Glob |\n|---|---|---|---|\n")
        for top in ["top1", "top3", "top5"]:
            s = stats["accuracy"]["semantic"][top]
            g = stats["accuracy"]["grep"][top]
            l = stats["accuracy"]["glob"][top]
            f.write(f"| {top.capitalize()} | {s[2]}% ({s[0]}/{s[1]}) | {g[2]}% ({g[0]}/{g[1]}) | {l[2]}% ({l[0]}/{l[1]}) |\n")

        f.write("\n### Timing (ms)\n\n")
        f.write("| Metric | Semantic | Grep | Glob |\n|---|---|---|---|\n")
        for metric in ["avg", "min", "max", "median"]:
            f.write(f"| {metric.capitalize()} | {stats['timing']['semantic'][metric]} | {stats['timing']['grep'][metric]} | {stats['timing']['glob'][metric]} |\n")

        misses = [r for r in results if r["has_targets"] and r["sem_top5"] is not True]
        if misses:
            f.write(f"\n## Semantic Search Misses (top-5): {len(misses)} questions\n\n")
            f.write("| # | Codebase | Question | Expected Targets |\n|---|---|---|---|\n")
            for i, r in enumerate(misses, 1):
                targets = ", ".join(f"`{t}``" for t in r["targets"][:3])
                f.write(f"| {i} | {r['codebase']} | {r['question']} | {targets} |\n")

    print(f"\nResults written to {path}")


if __name__ == "__main__":
    results, errors = run_benchmark()
    stats = compute_stats(results)
    print_summary(stats)
    export_markdown(results, stats)
