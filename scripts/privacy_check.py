from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

PATTERNS = [
    ("possible phone number", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("possible Bark key URL", re.compile(r"https://api\.day\.app/[A-Za-z0-9_-]{8,}")),
    ("possible custom Bark key URL", re.compile(r"https://[^/\s]+/+([A-Za-z0-9_-]{16,})(?:/|\s|$)")),
    ("possible token", re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?([A-Za-z0-9_+-]{12,})")),
    ("possible JWT", re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}")),
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
        file_path = Path(path)
        lower_name = file_path.name.lower()
        private_name = (
            lower_name == ".env"
            or (lower_name.startswith(".env.") and lower_name != ".env.example")
            or any(word in lower_name for word in ("cookie", "session", "credential", "private-key", "private_key"))
        )
        private_dir = bool(file_path.parts and file_path.parts[0] in {"data", "bark-data"})
        private_extension = file_path.suffix.lower() in {".sqlite3", ".db", ".pem", ".p12", ".pfx", ".key"}
        image_review = file_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"} and path != "app/static/eew-icon.png"
        if private_name or private_dir or private_extension or image_review:
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
                    if label == "possible custom Bark key URL" and file_path.name in {"package-lock.json", "npm-shrinkwrap.json"}:
                        continue
                    value = match if isinstance(match, str) else match[-1]
                    if value in ALLOWLIST:
                        continue
                    print(f"{path}:{lineno}: {label}")
                    failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
