# File: generate_trading_system_tree_v01.py
# Created: 2025-12-16 00:00 UTC
# Version Notes:
# - v01: Initial project tree generator for Ross Momentum Trading System
# - v02: Fixed CLI args, root/project separation, syntax cleanup

"""
PROJECT TREE GENERATOR
----------------------
This script generates the **entire folder structure** for the
"Ross Cameron–style Momentum Trading System".

It creates ONLY folders and placeholder __init__.py files.
NO business logic is created here.

WHY THIS EXISTS
---------------
You want to:
- start from a clean project folder
- guarantee the correct architecture
- copy/paste or regenerate safely
- align structure with frozen documentation

This script is intentionally simple and safe.
It can be run multiple times (idempotent behavior).

HOW TO USE
----------
python generate_trading_system_tree_v01.py \
    --root "C:/path/to/parent/folder" \
    --project-name trading_system_ross_momentum

RESULT
------
A fully scaffolded project tree ready for skeleton files.
"""

# ================================
# 1. Imports
# ================================

import os
import argparse
from datetime import datetime

# ================================
# 2. Helper Functions
# ================================

def create_dir(path: str):
    """Create directory if it does not exist."""
    os.makedirs(path, exist_ok=True)


def touch_init(path: str):
    """Create __init__.py to mark a Python package."""
    init_file = os.path.join(path, "__init__.py")
    if not os.path.exists(init_file):
        with open(init_file, "w", encoding="utf-8") as f:
            f.write(f"# Auto-generated package init ({datetime.utcnow()})\n")

# ================================
# 3. Project Tree Definition
# ================================

PROJECT_TREE = {
    "core_engine": {},
    "connectors": {},
    "data": {},
    "news": {},
    "scanner": {},
    "strategies": {
        "ross_momentum": {
            "patterns": {}
        }
    },
    "risk": {},
    "execution": {},
    "storage": {},
    "analytics": {},
    "utils": {},
    "tests": {
        "unit": {},
        "integration": {}
    }
}

# ================================
# 4. Tree Creation Logic
# ================================

def build_tree(base_path: str, tree: dict):
    """Recursively build directory tree."""
    for folder_name, children in tree.items():
        current_path = os.path.join(base_path, folder_name)
        create_dir(current_path)
        touch_init(current_path)

        if isinstance(children, dict):
            build_tree(current_path, children)

# ================================
# 5. Main Entry Point
# ================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate Ross Momentum trading system project tree"
    )

    parser.add_argument(
        "--root",
        required=False,
        default=os.getcwd(),
        help="Parent directory where the project folder will be created (default: current working directory)"
    )

    parser.add_argument(
        "--project-name",
        default="trading_system_ross_momentum",
        help="Name of the project root folder"
    )

    args = parser.parse_args()

    parent_root = os.path.abspath(args.root)
    project_root = os.path.join(parent_root, args.project_name)

    create_dir(project_root)

    print(f"[INFO] Creating project tree at: {project_root}")
    build_tree(project_root, PROJECT_TREE)
    print("[INFO] Project tree generation completed successfully.")

# ================================
# TEACHING NOTE
# ================================
# A clean, correct structure prevents architectural drift.
# Never write business logic before this tree exists.
