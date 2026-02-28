from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from ..data.paths import Paths

MAX_TREE_ROWS = 300
EXCLUDE_DIRS = {
    ".git",
    "__pycache__",
    "venv",
    "workspace",
    "logs",
    "memory",
    "exports",
    "models",
}
EXCLUDE_EXTS = {".md", ".jsonl", ".lock", ".csv", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf", ".ipynb"}


def _summary_table(title: str, rows: list[tuple[str, str]]) -> Table:
    t = Table(title=title, show_header=False)
    t.add_column("Field", no_wrap=True)
    t.add_column("Value", overflow="fold")
    for k, v in rows:
        t.add_row(k, v)
    return t


def _open_cmd(target: str) -> list[list[str]]:
    if sys.platform.startswith("darwin"):
        return [["open", target]]
    if os.name == "nt":
        return [["cmd", "/c", "start", "", target]]
    return [["xdg-open", target]]


def open_target(target: str) -> bool:
    for cmd in _open_cmd(target):
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception:
            continue
    return False


def _render_tree(console: Console, *, title: str, root: Path, max_depth: int | None, max_rows: int = MAX_TREE_ROWS) -> None:
    root = root.resolve()
    if not root.exists():
        console.print(_summary_table(f"{title} Summary", [("root", str(root)), ("status", "missing")]))
        return

    shown = dirs = files = 0
    truncated = False
    tree = Tree(Text(str(root), style=f"bold green link file://{root}"))

    def walk(parent: Tree, cur: Path, depth: int) -> None:
        nonlocal shown, dirs, files, truncated
        if truncated or (max_depth is not None and depth >= max_depth):
            return
        try:
            entries = sorted(cur.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except Exception:
            parent.add(Text("(unreadable)", style="yellow"))
            return
        for entry in entries:
            if shown >= max_rows:
                truncated = True
                return
            shown += 1
            style = "bold magenta" if entry.is_dir() else "white"
            label = Text(f"{entry.name}/" if entry.is_dir() else entry.name, style=f"{style} link file://{entry.resolve()}")
            child = parent.add(label)
            if entry.is_dir():
                dirs += 1
                walk(child, entry, depth + 1)
            else:
                files += 1

    walk(tree, root, 0)
    if truncated:
        tree.add(Text(f"... truncated at {max_rows} entries", style="yellow"))

    console.print(
        _summary_table(
            f"{title} Summary",
            [
                ("root", str(root)),
                ("depth", str(max_depth) if max_depth is not None else "full"),
                ("directories_shown", str(dirs)),
                ("files_shown", str(files)),
                ("entries_shown", str(shown)),
                ("truncated", "yes" if truncated else "no"),
            ],
        )
    )
    console.print(tree)


def structure_once(console: Console, depth: int) -> None:
    _render_tree(console, title="Solution Structure", root=Paths.resolve().home, max_depth=depth)


def workspace_once(console: Console, depth: int | None) -> None:
    _render_tree(console, title="Workspace Files", root=Paths.resolve().workspace, max_depth=depth)


def outputs_once(console: Console, depth: int | None) -> None:
    paths = Paths.resolve()
    _render_tree(console, title="Outputs: Workspace Reports", root=(paths.workspace / "reports"), max_depth=depth)
    _render_tree(console, title="Outputs: Host Logs", root=paths.logs_dir, max_depth=depth)
    _render_tree(console, title="Outputs: Host Artifacts", root=paths.artifacts_dir, max_depth=depth)


def show_folder_once(console: Console, root: Path, *, depth: int | None = 3, title: str = "Folder View") -> None:
    _render_tree(console, title=title, root=root, max_depth=depth)


def extract_depth(prompt: str, default: int = 4) -> int:
    m = re.search(r"(?:^|[\s-])(d|depth)\s*[:=]?\s*(\d{1,2})\b", (prompt or "").lower())
    if not m:
        return default
    try:
        return max(1, min(10, int(m.group(2))))
    except Exception:
        return default


def _should_skip(path: Path) -> bool:
    if set(path.parts).intersection(EXCLUDE_DIRS):
        return True
    return path.suffix.lower() in EXCLUDE_EXTS


def _iter_code_files(agent_root: Path) -> list[Path]:
    files: list[Path] = []
    for p in agent_root.rglob("*"):
        if p.is_file() and not _should_skip(p):
            files.append(p)
    return files


def loc_once(console: Console) -> None:
    paths = Paths.resolve()
    files = _iter_code_files(paths.agent_root)
    total_lines = 0
    unreadable = 0
    for f in files:
        try:
            with f.open("r", encoding="utf-8", errors="ignore") as handle:
                total_lines += sum(1 for _ in handle)
        except Exception:
            unreadable += 1
    console.print(
        _summary_table(
            "Lines of Code Summary",
            [
                ("root", str(paths.agent_root)),
                ("files_counted", str(len(files))),
                ("lines_total", str(total_lines)),
                ("unreadable_files", str(unreadable)),
            ],
        )
    )
