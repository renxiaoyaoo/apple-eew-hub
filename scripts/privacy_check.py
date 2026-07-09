from __future__ import annotations

import re
import os
import subprocess
import sys

PATTERNS = [
    ("possible phone number", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("possible Bark key URL", re.compile(r"https://api\.day\.app/[A-Za-z0-9_-]{8,}")),
    ("possible token", re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?([A-Za-z0-9_+-]{12,})")),
    ("possible email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
]

ALLOWLIST = {
    "account@example.com",
    "localStorage",
}


def files_to_check() -> list[str]:
    try:
        subprocess.check_output(["git", "rev-parse", "--is-inside-work-tree"], stderr=subprocess.DEVNULL, text=True)
        out = subprocess.check_output(["git", "diff", "--cached", "--name-only"], stderr=subprocess.DEVNULL, text=True)
        files = [line.strip() for line in out.splitlines() if line.strip()]
        if files:
            return files
    except subprocess.CalledProcessError:
        pass

    skipped_dirs = {".git", ".venv", "__pycache__", ".pytest_cache", "data", "bark-data", "dist", "node_modules", "public"}
    result: list[str] = []
    for root, dirs, names in os.walk("."):
        dirs[:] = [d for d in dirs if d not in skipped_dirs]
        for name in names:
            if name == ".env" or name.endswith((".sqlite3", ".db", ".pyc")):
                continue
            result.append(os.path.join(root, name).removeprefix("./"))
    return result


def main() -> int:
    failed = False
    for path in files_to_check():
        if path.startswith("data/") or path.endswith((".sqlite3", ".db")) or path == ".env":
            print(f"{path}: runtime/private file risk")
            failed = True
            continue
        try:
            text = open(path, "r", encoding="utf-8").read()
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for label, pattern in PATTERNS:
                for match in pattern.findall(line):
                    value = match if isinstance(match, str) else match[-1]
                    if value in ALLOWLIST:
                        continue
                    print(f"{path}:{lineno}: {label}")
                    failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
