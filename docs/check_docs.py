from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS_FILE = ROOT / "docs" / "stale_path_patterns.txt"
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _markdown_files() -> list[Path]:
    try:
        tracked = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "*.md"],
            capture_output=True,
            text=True,
            check=True,
        )
        untracked = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "--others", "--exclude-standard", "*.md"],
            capture_output=True,
            text=True,
            check=True,
        )
        seen: set[Path] = set()
        files = []
        for line in (tracked.stdout + "\n" + untracked.stdout).splitlines():
            rel = line.strip()
            if not rel:
                continue
            p = (ROOT / rel).resolve()
            if p.exists() and p not in seen:
                seen.add(p)
                files.append(p)
        return sorted(files)
    except Exception:
        return sorted(ROOT.rglob("*.md"))


def _normalize_target(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()
    # Support markdown links with optional title: path "title"
    if " " in target and not target.startswith(("http://", "https://")):
        target = target.split(" ", 1)[0].strip()
    return target


def _check_links(files: list[Path]) -> list[str]:
    errors: list[str] = []
    for md in files:
        text = md.read_text(encoding="utf-8", errors="ignore")
        for m in MARKDOWN_LINK_RE.finditer(text):
            raw = m.group(1)
            target = _normalize_target(raw)
            if not target:
                continue
            if target.startswith(("http://", "https://", "mailto:", "tel:")):
                continue
            if target.startswith("#"):
                continue
            path_only = target.split("#", 1)[0]
            if not path_only:
                continue
            resolved = (md.parent / path_only).resolve()
            if not resolved.exists():
                rel = md.relative_to(ROOT)
                errors.append(f"Broken link in {rel}: {raw}")
    return errors


def _load_stale_patterns() -> list[str]:
    if not PATTERNS_FILE.exists():
        return []
    lines = PATTERNS_FILE.read_text(encoding="utf-8").splitlines()
    patterns = []
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        patterns.append(s)
    return patterns


def _check_stale_paths(files: list[Path], patterns: list[str]) -> list[str]:
    errors: list[str] = []
    if not patterns:
        return errors
    for md in files:
        text = md.read_text(encoding="utf-8", errors="ignore")
        for pattern in patterns:
            if pattern in text:
                rel = md.relative_to(ROOT)
                errors.append(f"Stale path reference in {rel}: {pattern}")
    return errors


def main() -> int:
    files = _markdown_files()
    if not files:
        print("No markdown files found.")
        return 0

    link_errors = _check_links(files)
    stale_errors = _check_stale_paths(files, _load_stale_patterns())
    errors = link_errors + stale_errors

    print(f"Docs check scanned {len(files)} markdown files.")
    if errors:
        for err in errors:
            print(f"ERROR: {err}")
        return 1

    print("Docs check passed: no broken links and no stale path references.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
