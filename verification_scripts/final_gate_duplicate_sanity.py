from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check_modules() -> int:
    src_root = ROOT / "src"
    files = [p for p in src_root.rglob("*.py") if p.name != "__init__.py"]
    names = [p.name for p in files]
    dupes = sorted((name, count) for name, count in Counter(names).items() if count > 1)
    risky = []

    for path in files:
        rel = path.relative_to(src_root)
        if len(rel.parts) == 1:
            risky.append(path.name)
    risky_dupes = sorted(name for name, count in Counter(risky).items() if count > 1)

    print("# duplicate python module filenames under src/")
    print("# note: same filename in different packages is common and not import-shadow risk")
    print(f"risky_duplicates={risky_dupes}")
    print("all_duplicate_filenames=")
    if not dupes:
        print("  []")
    else:
        for name, count in dupes:
            print(f"- {name}: {count}")
            for p in sorted(src_root.rglob(name)):
                print(f"    - {p.relative_to(ROOT)}")
    return 1 if risky_dupes else 0


def _extract_registry_keys(raw: str, section: str) -> list[str]:
    keys: list[str] = []
    in_section = False
    for line in raw.splitlines():
        if re.match(rf"^{section}:\s*$", line):
            in_section = True
            continue
        if in_section and re.match(r"^[A-Za-z_]+:\s*$", line):
            break
        if in_section:
            m = re.match(r"^\s{2}([A-Z]\d{1,2}):", line)
            if m:
                keys.append(m.group(1))
    return keys


def check_registry() -> int:
    rc = 0
    registry_path = ROOT / "src" / "integrity" / "epoch_verification_registry.yaml"
    raw = registry_path.read_text(encoding="utf-8")

    print("# duplicate E*/M*/P* keys in epoch_verification_registry.yaml")
    for section in ("core_epochs", "metadata_epochs", "strategies"):
        keys = _extract_registry_keys(raw, section)
        dupes = sorted(k for k, c in Counter(keys).items() if c > 1)
        print(f"{section}: duplicates={dupes}")
        if dupes:
            rc = 1

    print("\n# strategy registration duplicate sanity from src/strategy/strategy_runner.py")
    runner_src = (ROOT / "src" / "strategy" / "strategy_runner.py").read_text(encoding="utf-8")
    registrations = re.findall(
        r"StrategyRegistration\(\s*\"([^\"]+)\"\s*,\s*([A-Za-z_][A-Za-z0-9_]*)\s*,\s*\"([^\"]+)\"",
        runner_src,
        flags=re.MULTILINE,
    )
    names = [r[0] for r in registrations]
    classes = [r[1] for r in registrations]
    keys = [r[2] for r in registrations]
    for label, values in (("strategy_name", names), ("strategy_class", classes), ("selected_key", keys)):
        dupes = sorted(v for v, c in Counter(values).items() if c > 1)
        print(f"{label}: duplicates={dupes}")
        if dupes:
            rc = 1
    print(f"total_registered={len(registrations)}")
    return rc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", choices=["modules", "registry"], required=True)
    args = parser.parse_args()
    if args.check == "modules":
        return check_modules()
    return check_registry()


if __name__ == "__main__":
    raise SystemExit(main())
