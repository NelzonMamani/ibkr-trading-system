#!/usr/bin/env python3
"""
repo_size_report.py

Reports:
- Total repository size
- Size per top-level folder
- Size per file (largest first)

Ignores:
- .git directory by default
"""

import os
from pathlib import Path
from collections import defaultdict

IGNORE_DIRS = {".git", ".venv", "__pycache__"}

def format_size(num_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num_bytes < 1024:
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.2f} PB"

def walk_repo(root: Path):
    total_size = 0
    folder_sizes = defaultdict(int)
    file_sizes = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]

        for filename in filenames:
            file_path = Path(dirpath) / filename
            try:
                size = file_path.stat().st_size
            except OSError:
                continue

            total_size += size
            file_sizes.append((file_path, size))

            try:
                top_level = file_path.relative_to(root).parts[0]
            except IndexError:
                top_level = "."
            folder_sizes[top_level] += size

    return total_size, folder_sizes, file_sizes

def main():
    root = Path.cwd()

    print(f"\nRepository: {root}")
    print("-" * 60)

    total_size, folder_sizes, file_sizes = walk_repo(root)

    print(f"\nTOTAL REPOSITORY SIZE: {format_size(total_size)}")

    print("\nSIZE BY TOP-LEVEL FOLDER:")
    for folder, size in sorted(folder_sizes.items(), key=lambda x: x[1], reverse=True):
        print(f"  {folder:<30} {format_size(size)}")

    print("\nTOP 20 LARGEST FILES:")
    for path, size in sorted(file_sizes, key=lambda x: x[1], reverse=True)[:20]:
        rel = path.relative_to(root)
        print(f"  {str(rel):<60} {format_size(size)}")

if __name__ == "__main__":
    main()
