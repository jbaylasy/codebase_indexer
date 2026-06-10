import re


def parse_questions(filepath):
    """Parse numbered questions from the questions.md file, grouped by codebase section.

    Maps section headers to codebase directory names. The "infrastructure" section
    header maps to the "card_infrastructure" directory name.

    Args:
        filepath: Path to the questions.md file.

    Returns:
        A dict mapping codebase names to lists of question strings.
    """
    codebase_map = {
        "card shop": "card_shop",
        "card collection": "card_collection",
        "infrastructure": "card_infrastructure",
        "scripts": "card_infrastructure",
    }

    questions = {}
    current_codebase = None

    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()

            if line.startswith("# ") and not line.startswith("## "):
                name = re.sub(r'[^\w\s]', '', line.lstrip("# ")).strip().lower()
                for key, mapped in codebase_map.items():
                    if key in name:
                        current_codebase = mapped
                        if current_codebase not in questions:
                            questions[current_codebase] = []
                        break
                continue

            match = re.match(r'^\d+\.\s+(.+)', line)
            if match and current_codebase:
                questions[current_codebase].append(match.group(1))

    return questions
