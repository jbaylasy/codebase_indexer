import time
import subprocess
import glob as glob_mod
import os
import re
import json
import statistics
from code_index.parser import parse_questions
from code_index.database import init_client, get_collection
from code_index.search import search_code
from code_index.embedder import warm_up

STOP_WORDS = {
    "the", "is", "a", "an", "where", "find", "what", "how", "does", "in",
    "of", "and", "to", "for", "that", "this", "it", "on", "with", "as",
    "by", "from", "or", "be", "are", "was", "were", "been", "being",
    "can", "could", "should", "would", "which", "who", "when", "why",
    "do", "did", "has", "have", "had", "will", "may", "might", "shall",
    "my", "your", "his", "her", "its", "our", "their", "i", "me", "we",
    "you", "he", "she", "they", "us", "them", "not", "no", "so", "if",
    "but", "than", "too", "very", "just", "about", "up", "out", "all",
    "some", "any", "each", "every", "both", "few", "more", "most",
    "other", "such", "only", "same", "also", "then", "there", "here",
    "into", "over", "after", "before", "between", "under", "again",
    "further", "once", "during", "am", "at", "these", "those",
}

SKIP_TARGETS = {
    "SELECT", "INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP",
    "JOIN", "WHERE", "FROM", "GROUP BY", "ORDER BY", "HAVING", "LIMIT",
    "POST", "GET", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS",
    "HTTP", "HTTPS", "SQL", "JSON", "CSV", "API", "URL", "REST",
    "AND", "OR", "NOT", "NULL", "TRUE", "FALSE", "ON", "OFF",
    "ASC", "DESC", "DISTINCT", "UNION", "EXCEPT", "INTERSECT",
    "INNER", "OUTER", "LEFT", "RIGHT", "FULL", "CROSS", "NATURAL",
    "LATERAL", "VALUES", "SET", "INTO", "TABLE", "INDEX", "VIEW",
    "PRIMARY", "FOREIGN", "KEY", "UNIQUE", "CONSTRAINT", "DEFAULT",
    "CHECK", "REFERENCES", "CASCADE", "SERIAL", "BIGSERIAL",
    "BOOLEAN", "INTEGER", "TEXT", "VARCHAR", "TIMESTAMP", "DATE",
    "JSONB", "FLOAT", "NUMERIC", "BIGINT", "SMALLINT", "CHAR",
    "postgresql", "postgres", "sqlite", "docker", "python",
}

CODEBASE_DIR_MAP = {
    "card_infrastructure": "test_codebase/card_infrastructure",
    "card_shop": "test_codebase/card_shop",
    "card_collection": "test_codebase/card_collection",
    "financial_visuals": "test_codebase/financial_visuals",
}

COLLECTION_MAP = {
    "card_infrastructure": "card_infrastructure_index",
    "card_shop": "card_shop_index",
    "card_collection": "card_collection_index",
    "financial_visuals": "financial_visuals_index",
}


def extract_keywords(query):
    words = query.lower().replace("?", "").replace(".", "").replace(",", "").split()
    return [w for w in words if w not in STOP_WORDS and len(w) > 2][:3]


def extract_targets(question):
    raw = re.findall(r'`([^`]+)`', question)
    targets = []
    for t in raw:
        if t.upper().strip() not in SKIP_TARGETS and len(t.strip()) > 1:
            targets.append(t.strip())
    if not targets and question in _ground_truth_map:
        gt = _ground_truth_map[question]
        targets = gt.get("expected_keywords", [])[:5]
    return targets


_ground_truth_map = {}


def load_ground_truth():
    global _ground_truth_map
    gt_path = os.path.join(os.path.dirname(__file__), "benchmark_ground_truth.json")
    if os.path.exists(gt_path):
        with open(gt_path, "r") as f:
            entries = json.load(f)
        for entry in entries:
            _ground_truth_map[entry["question"]] = entry


def run_semantic_search(query, collection, n_results=5):
    t0 = time.perf_counter()
    result = search_code(query, collection, n_results=n_results)
    elapsed = time.perf_counter() - t0
    return result["results"], elapsed


def run_grep_search(query, codebase_dir, max_results=5):
    keywords = extract_keywords(query)
    if not keywords:
        return [], 0.0
    results = []
    t0 = time.perf_counter()
    for kw in keywords[:3]:
        try:
            proc = subprocess.run(
                ["grep", "-rn", "--include=*.py", "--include=*.ts", "--include=*.tsx",
                 "--include=*.jsx", "--include=*.js", "--include=*.sql",
                 "--include=*.yml", "--include=*.yaml", "--include=*.env",
                 "--include=*.json", "--include=*.md", "--include=*.sh",
                 "--include=*.css", "--include=*.html", "--include=*.conf",
                 "--include=*.toml", "--include=*.cfg", "--include=*.ini",
                 "--include=*.txt", "--include=*.dockerfile", "--include=*.ex",
                 "--include=*.exs", "--include=*.rb", "--include=*.go",
                 "-l", kw, codebase_dir],
                capture_output=True, text=True, timeout=10,
            )
            for line in proc.stdout.strip().split("\n"):
                if line:
                    results.append({"file": line.strip(), "name": "", "type": "", "code": ""})
        except subprocess.TimeoutExpired:
            pass
    elapsed = time.perf_counter() - t0
    return results[:max_results], elapsed


def run_glob_search(query, codebase_dir, max_results=5):
    keywords = extract_keywords(query)
    if not keywords:
        return [], 0.0
    results = []
    t0 = time.perf_counter()
    for kw in keywords[:3]:
        patterns = [
            os.path.join(codebase_dir, "**", f"*{kw}*"),
        ]
        for pattern in patterns:
            matches = glob_mod.glob(pattern, recursive=True)
            for m in matches:
                if os.path.isfile(m):
                    results.append({"file": m, "name": "", "type": "", "code": ""})
    elapsed = time.perf_counter() - t0
    return results[:max_results], elapsed


def check_match_any(results, targets, top_n):
    if not targets:
        return None
    lower_targets = [t.lower() for t in targets]
    for i, r in enumerate(results[:top_n]):
        file_val = (r.get("file") or "").lower()
        name_val = (r.get("name") or "").lower()
        code_val = (r.get("code") or "").lower()
        combined = file_val + " " + name_val + " " + code_val
        for tgt in lower_targets:
            if tgt.lower() in combined:
                return i + 1
    return 0


def run_full_benchmark():
    print("Parsing questions from questions.md...")
    load_ground_truth()
    questions_by_codebase = parse_questions("questions.md")

    total_qs = sum(len(v) for v in questions_by_codebase.values())
    print(f"Found {total_qs} questions across {len(questions_by_codebase)} codebases")

    print("Warming up embedder...")
    warm_up()

    print("Initializing database client...")
    client = init_client("./code_index_db")

    collections = {}
    for codebase, coll_name in COLLECTION_MAP.items():
        collections[codebase] = get_collection(client, coll_name)
        count = collections[codebase].count_rows()
        print(f"  {coll_name}: {count} chunks")

    results = []
    errors = []

    for codebase, questions in questions_by_codebase.items():
        codebase_dir = CODEBASE_DIR_MAP.get(codebase, "")
        collection = collections.get(codebase)
        if not collection or not codebase_dir:
            print(f"  Skipping {codebase}: no collection or directory")
            continue

        print(f"\nRunning {len(questions)} questions for {codebase}...")

        for qi, question in enumerate(questions):
            targets = extract_targets(question)
            row = {
                "question": question,
                "codebase": codebase,
                "targets": targets,
                "has_targets": len(targets) > 0,
                "sem_top1": None,
                "sem_top3": None,
                "sem_top5": None,
                "grep_top1": None,
                "grep_top3": None,
                "grep_top5": None,
                "glob_top1": None,
                "glob_top3": None,
                "glob_top5": None,
                "sem_time": 0.0,
                "grep_time": 0.0,
                "glob_time": 0.0,
                "error": None,
            }

            try:
                sem_results, sem_time = run_semantic_search(question, collection, n_results=5)
                row["sem_time"] = sem_time

                if targets:
                    pos = check_match_any(sem_results, targets, 1)
                    row["sem_top1"] = pos is not None and pos > 0
                    pos = check_match_any(sem_results, targets, 3)
                    row["sem_top3"] = pos is not None and pos > 0
                    pos = check_match_any(sem_results, targets, 5)
                    row["sem_top5"] = pos is not None and pos > 0
            except Exception as e:
                row["error"] = f"semantic: {e}"
                errors.append((codebase, qi, question, str(e)))

            try:
                grep_results, grep_time = run_grep_search(question, codebase_dir, max_results=5)
                row["grep_time"] = grep_time

                if targets:
                    pos = check_match_any(grep_results, targets, 1)
                    row["grep_top1"] = pos is not None and pos > 0
                    pos = check_match_any(grep_results, targets, 3)
                    row["grep_top3"] = pos is not None and pos > 0
                    pos = check_match_any(grep_results, targets, 5)
                    row["grep_top5"] = pos is not None and pos > 0
            except Exception as e:
                row["error"] = (row["error"] or "") + f" grep: {e}"
                errors.append((codebase, qi, question, str(e)))

            try:
                glob_results, glob_time = run_glob_search(question, codebase_dir, max_results=5)
                row["glob_time"] = glob_time

                if targets:
                    pos = check_match_any(glob_results, targets, 1)
                    row["glob_top1"] = pos is not None and pos > 0
                    pos = check_match_any(glob_results, targets, 3)
                    row["glob_top3"] = pos is not None and pos > 0
                    pos = check_match_any(glob_results, targets, 5)
                    row["glob_top5"] = pos is not None and pos > 0
            except Exception as e:
                row["error"] = (row["error"] or "") + f" glob: {e}"
                errors.append((codebase, qi, question, str(e)))

            results.append(row)
            status = "OK" if not row["error"] else "ERR"
            tgt_str = ",".join(targets[:2]) if targets else "(no target)"
            sem_hit = "Y" if row["sem_top5"] else ("N" if row["sem_top5"] is not None else "-")
            print(f"  [{qi+1}/{len(questions)}] {status} sem@5:{sem_hit} | {tgt_str}")

    return results, errors


def compute_stats(results):
    with_targets = [r for r in results if r["has_targets"]]
    n_total = len(results)
    n_targeted = len(with_targets)

    stats = {"total_questions": n_total, "targeted_questions": n_targeted}

    for method in ["sem", "grep", "glob"]:
        for top_n in ["top1", "top3", "top5"]:
            key = f"{method}_{top_n}"
            hits = sum(1 for r in with_targets if r.get(key) is True)
            misses = sum(1 for r in with_targets if r.get(key) is False)
            eligible = hits + misses
            pct = (hits / eligible * 100) if eligible > 0 else 0
            stats[f"{method}_{top_n}_hits"] = hits
            stats[f"{method}_{top_n}_eligible"] = eligible
            stats[f"{method}_{top_n}_pct"] = pct

    for method in ["sem", "grep", "glob"]:
        times = [r[f"{method}_time"] * 1000 for r in results if r[f"{method}_time"] > 0]
        if times:
            stats[f"{method}_avg_ms"] = statistics.mean(times)
            stats[f"{method}_min_ms"] = min(times)
            stats[f"{method}_max_ms"] = max(times)
            stats[f"{method}_median_ms"] = statistics.median(times)
        else:
            stats[f"{method}_avg_ms"] = 0
            stats[f"{method}_min_ms"] = 0
            stats[f"{method}_max_ms"] = 0
            stats[f"{method}_median_ms"] = 0

    return stats


def print_summary(results, stats):
    print("\n" + "=" * 120)
    print("FULL BENCHMARK RESULTS")
    print("=" * 120)

    header = f"{'#':<4} {'CB':<6} {'Tgt':<4} {'S1':>3} {'S3':>3} {'S5':>3} {'G1':>3} {'G3':>3} {'G5':>3} {'L1':>3} {'L3':>3} {'L5':>3} {'Sms':>7} {'Gms':>7} {'Lms':>7}  Question"
    print(header)
    print("-" * 120)

    for i, r in enumerate(results):
        def tf(v):
            if v is True:
                return "Y"
            elif v is False:
                return "N"
            return "-"
        cb = r["codebase"][:6]
        tgt = "Y" if r["has_targets"] else "-"
        s1, s3, s5 = tf(r["sem_top1"]), tf(r["sem_top3"]), tf(r["sem_top5"])
        g1, g3, g5 = tf(r["grep_top1"]), tf(r["grep_top3"]), tf(r["grep_top5"])
        l1, l3, l5 = tf(r["glob_top1"]), tf(r["glob_top3"]), tf(r["glob_top5"])
        sms = f"{r['sem_time']*1000:.1f}"
        gms = f"{r['grep_time']*1000:.1f}"
        lms = f"{r['glob_time']*1000:.1f}"
        q = r["question"][:50]
        print(f"{i+1:<4} {cb:<6} {tgt:<4} {s1:>3} {s3:>3} {s5:>3} {g1:>3} {g3:>3} {g5:>3} {l1:>3} {l3:>3} {l5:>3} {sms:>7} {gms:>7} {lms:>7}  {q}")

    print()
    print("=" * 80)
    print("SUMMARY STATISTICS")
    print("=" * 80)
    print(f"Total questions:              {stats['total_questions']}")
    print(f"Questions with targets:       {stats['targeted_questions']}")
    print(f"Questions without targets:    {stats['total_questions'] - stats['targeted_questions']}")
    print()

    print(f"{'Metric':<25} {'Semantic':>12} {'Grep':>12} {'Glob':>12}")
    print("-" * 61)
    for top_n, label in [("top1", "Top-1"), ("top3", "Top-3"), ("top5", "Top-5")]:
        sp = stats[f"sem_{top_n}_pct"]
        gp = stats[f"grep_{top_n}_pct"]
        lp = stats[f"glob_{top_n}_pct"]
        sh = stats[f"sem_{top_n}_hits"]
        gh = stats[f"grep_{top_n}_hits"]
        lh = stats[f"glob_{top_n}_hits"]
        se = stats[f"sem_{top_n}_eligible"]
        ge = stats[f"grep_{top_n}_eligible"]
        le = stats[f"glob_{top_n}_eligible"]
        print(f"{label + ' Accuracy':<25} {sp:>11.1f}% {gp:>11.1f}% {lp:>11.1f}%")
        print(f"{label + ' (hits/eligible)':<25} {sh:>5}/{se:<5} {gh:>5}/{ge:<5} {lh:>5}/{le:<5}")

    print()
    print(f"{'Timing (ms)':<25} {'Semantic':>12} {'Grep':>12} {'Glob':>12}")
    print("-" * 61)
    for metric in ["avg", "min", "max", "median"]:
        label = metric.capitalize()
        sv = stats[f"sem_{metric}_ms"]
        gv = stats[f"grep_{metric}_ms"]
        lv = stats[f"glob_{metric}_ms"]
        print(f"{label:<25} {sv:>12.2f} {gv:>12.2f} {lv:>12.2f}")

    print()
    print("SEMANTIC SEARCH MISSES (not found in top-5):")
    print("-" * 80)
    misses = [r for r in results if r["has_targets"] and r.get("sem_top5") is False]
    if misses:
        for i, r in enumerate(misses):
            targets_str = ", ".join(r["targets"][:3])
            print(f"  {i+1}. [{r['codebase']}] {r['question'][:80]}")
            print(f"     Expected: {targets_str}")
    else:
        print("  None! All targeted questions found in top-5.")


def export_markdown(results, stats):
    lines = [
        "# Full Benchmark Results: Semantic Search vs Grep vs Glob (220 Questions)",
        "",
        f"_Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}_",
        "",
        "## Summary",
        "",
        f"- **Total questions:** {stats['total_questions']}",
        f"- **Questions with extractable targets:** {stats['targeted_questions']}",
        f"- **Questions without targets (timed only):** {stats['total_questions'] - stats['targeted_questions']}",
        "",
        "### Accuracy",
        "",
        "| Metric | Semantic | Grep | Glob |",
        "|---|---|---|---|",
    ]

    for top_n, label in [("top1", "Top-1"), ("top3", "Top-3"), ("top5", "Top-5")]:
        sp = stats[f"sem_{top_n}_pct"]
        gp = stats[f"grep_{top_n}_pct"]
        lp = stats[f"glob_{top_n}_pct"]
        sh = stats[f"sem_{top_n}_hits"]
        se = stats[f"sem_{top_n}_eligible"]
        gh = stats[f"grep_{top_n}_hits"]
        ge = stats[f"grep_{top_n}_eligible"]
        lh = stats[f"glob_{top_n}_hits"]
        le = stats[f"glob_{top_n}_eligible"]
        lines.append(
            f"| {label} | {sp:.1f}% ({sh}/{se}) | {gp:.1f}% ({gh}/{ge}) | {lp:.1f}% ({lh}/{le}) |"
        )

    lines.append("")
    lines.append("### Timing (ms)")
    lines.append("")
    lines.append("| Metric | Semantic | Grep | Glob |")
    lines.append("|---|---|---|---|")
    for metric in ["avg", "min", "max", "median"]:
        label = metric.capitalize()
        sv = stats[f"sem_{metric}_ms"]
        gv = stats[f"grep_{metric}_ms"]
        lv = stats[f"glob_{metric}_ms"]
        lines.append(f"| {label} | {sv:.2f} | {gv:.2f} | {lv:.2f} |")

    lines.append("")
    lines.append("## Semantic Search Misses (top-5)")
    lines.append("")
    misses = [r for r in results if r["has_targets"] and r.get("sem_top5") is False]
    if misses:
        lines.append("| # | Codebase | Question | Expected Targets |")
        lines.append("|---|---|---|---|")
        for i, r in enumerate(misses):
            targets_str = ", ".join(f"`{t}`" for t in r["targets"][:3])
            lines.append(f"| {i+1} | {r['codebase']} | {r['question']} | {targets_str} |")
    else:
        lines.append("All targeted questions found in top-5!")

    lines.append("")
    lines.append("## Detailed Results")
    lines.append("")
    lines.append("| # | CB | Tgt | S1 | S3 | S5 | G1 | G3 | G5 | L1 | L3 | L5 | Sem(ms) | Grep(ms) | Glob(ms) | Question |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")

    for i, r in enumerate(results):
        def tf(v):
            if v is True:
                return "Y"
            elif v is False:
                return "N"
            return "-"
        tgt = "Y" if r["has_targets"] else "-"
        row = (
            f"| {i+1} | {r['codebase'][:6]} | {tgt} "
            f"| {tf(r['sem_top1'])} | {tf(r['sem_top3'])} | {tf(r['sem_top5'])} "
            f"| {tf(r['grep_top1'])} | {tf(r['grep_top3'])} | {tf(r['grep_top5'])} "
            f"| {tf(r['glob_top1'])} | {tf(r['glob_top3'])} | {tf(r['glob_top5'])} "
            f"| {r['sem_time']*1000:.1f} | {r['grep_time']*1000:.1f} | {r['glob_time']*1000:.1f} "
            f"| {r['question']} |"
        )
        lines.append(row)

    lines.append("")
    lines.append("## Legend")
    lines.append("")
    lines.append("- **CB**: Codebase (card_sh=card_shop, card_c=card_collection, card_i=card_infrastructure, finan=financial_visuals)")
    lines.append("- **Tgt**: Has extractable backtick target(s)")
    lines.append("- **S/G/L**: Semantic / Grep / Glob")
    lines.append("- **1/3/5**: Top-1, Top-3, Top-5 accuracy")
    lines.append("- **Y**: Target found, **N**: Target not found, **-**: No target to check")
    lines.append("")

    with open("benchmark_results.md", "w") as f:
        f.write("\n".join(lines))
    print(f"\nResults exported to benchmark_results.md")


if __name__ == "__main__":
    results, errors = run_full_benchmark()
    stats = compute_stats(results)
    print_summary(results, stats)
    export_markdown(results, stats)

    if errors:
        print(f"\n\nERRORS ENCOUNTERED ({len(errors)}):")
        for codebase, qi, question, error in errors:
            print(f"  [{codebase}] Q{qi+1}: {error}")
