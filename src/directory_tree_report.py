"""
Directory Tree Report Generator

- Recursively scans a directory
- Prints a clean tree structure of all folders and files
- Excludes common development folders (.idea, .venv, .git)
- Can run from anywhere as a standalone script
"""

from pathlib import Path


# ==============================
# CONFIGURATION
# ==============================

# OPTION 1: ABSOLUTE PATH (comment out if running from project root)
ROOT_DIRECTORY = Path(r"C:\Users\nelzo\PycharmProjectsDec2025\ibkr-trading-system")

# OPTION 2: PROJECT ROOT (uncomment if script is inside the project)
# ROOT_DIRECTORY = Path(__file__).resolve().parent

# Output report file
OUTPUT_FILE = "directory_tree_report.txt"

# Folders to exclude
EXCLUDED_DIRS = {
    ".idea",
    ".venv",
    ".git",
    "__pycache__",
}


# ==============================
# TREE GENERATION LOGIC
# ==============================

def generate_tree(path: Path, prefix: str = "") -> list[str]:
    """
    Recursively builds a tree representation of the directory,
    excluding specified folders.
    """
    tree_lines = []

    try:
        entries = sorted(
            path.iterdir(),
            key=lambda p: (p.is_file(), p.name.lower())
        )
    except PermissionError:
        return tree_lines

    # Filter excluded directories
    entries = [
        e for e in entries
        if not (e.is_dir() and e.name in EXCLUDED_DIRS)
    ]

    for index, entry in enumerate(entries):
        connector = "└── " if index == len(entries) - 1 else "├── "
        tree_lines.append(f"{prefix}{connector}{entry.name}")

        if entry.is_dir():
            extension = "    " if index == len(entries) - 1 else "│   "
            tree_lines.extend(
                generate_tree(entry, prefix + extension)
            )

    return tree_lines


# ==============================
# MAIN EXECUTION
# ==============================

def main():
    if not ROOT_DIRECTORY.exists():
        raise FileNotFoundError(f"Directory does not exist: {ROOT_DIRECTORY}")

    header = f"{ROOT_DIRECTORY.name}/"
    tree = generate_tree(ROOT_DIRECTORY)

    report_lines = [header] + tree
    report_text = "\n".join(report_lines)

    # Print to console
    print(report_text)

    # Save to file
    Path(OUTPUT_FILE).write_text(report_text, encoding="utf-8")

    print(f"\nReport saved to: {Path(OUTPUT_FILE).resolve()}")


if __name__ == "__main__":
    main()
