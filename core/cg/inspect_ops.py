from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from .paths import Paths

MAX_TREE_ROWS = 300


def open_for_review(path: Path) -> bool:
    cmds: list[list[str]] = []
    if sys.platform.startswith("darwin"):
        cmds.append(["open", str(path)])
    elif os.name == "nt":
        cmds.append(["cmd", "/c", "start", "", str(path)])
    else:
        cmds.append(["xdg-open", str(path)])

    for cmd in cmds:
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception:
            continue
    return False


def open_target(target: str) -> bool:
    cmds: list[list[str]] = []
    if sys.platform.startswith("darwin"):
        cmds.append(["open", target])
    elif os.name == "nt":
        cmds.append(["cmd", "/c", "start", "", target])
    else:
        cmds.append(["xdg-open", target])
    for cmd in cmds:
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception:
            continue
    return False


def _render_tree(console: Console, *, title: str, root: Path, max_depth: Optional[int], max_rows: int = MAX_TREE_ROWS) -> None:
    root = root.resolve()
    shown_nodes = 0
    dir_count = 0
    file_count = 0
    truncated = False

    if not root.exists():
        console.print(f"\n------------ {title} ------------")
        console.print(Text(str(root), style=f"link file://{root}"))
        console.print("missing")
        return

    tree = Tree(Text(str(root), style=f"link file://{root}"))

    def _walk(parent: Tree, cur: Path, depth: int) -> None:
        nonlocal shown_nodes, dir_count, file_count, truncated
        if truncated:
            return
        if max_depth is not None and depth >= max_depth:
            return
        try:
            entries = sorted(cur.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except Exception:
            parent.add(Text("(unreadable)"))
            return
        for entry in entries:
            if shown_nodes >= max_rows:
                truncated = True
                return
            shown_nodes += 1
            label = Text(f"{entry.name}/" if entry.is_dir() else entry.name, style=f"link file://{entry.resolve()}")
            child = parent.add(label)
            if entry.is_dir():
                dir_count += 1
                _walk(child, entry, depth + 1)
            else:
                file_count += 1

    _walk(tree, root, 0)
    if truncated:
        tree.add(Text(f"... output truncated at {max_rows} entries; refine with -d or inspect a narrower path"))

    summary = Table(title=f"{title} Summary", show_header=False)
    summary.add_column("Field", no_wrap=True)
    summary.add_column("Value", overflow="fold")
    summary.add_row("root", str(root))
    summary.add_row("depth", str(max_depth) if max_depth is not None else "full")
    summary.add_row("directories_shown", str(dir_count))
    summary.add_row("files_shown", str(file_count))
    summary.add_row("entries_shown", str(shown_nodes))
    summary.add_row("truncated", "yes" if truncated else "no")
    console.print(summary)
    console.print(tree)


def structure_once(console: Console, depth: int) -> None:
    paths = Paths.resolve()
    _render_tree(console, title="Solution Structure", root=paths.home, max_depth=depth)


def workspace_once(console: Console, depth: Optional[int]) -> None:
    paths = Paths.resolve()
    _render_tree(console, title="Workspace Files", root=paths.workspace, max_depth=depth)


def outputs_once(console: Console, depth: Optional[int]) -> None:
    paths = Paths.resolve()
    reports_dir = (paths.workspace / "reports").resolve()
    _render_tree(console, title="Outputs: Workspace Reports", root=reports_dir, max_depth=depth)
    _render_tree(console, title="Outputs: Host Logs", root=paths.logs_dir, max_depth=depth)
    _render_tree(console, title="Outputs: Host Artifacts", root=paths.artifacts_dir, max_depth=depth)


def extract_depth(prompt: str, default: int = 4) -> int:
    m = re.search(r"(?:^|[\s-])(d|depth)\s*[:=]?\s*(\d{1,2})\b", prompt.lower())
    if not m:
        return default
    try:
        val = int(m.group(2))
        return max(1, min(10, val))
    except Exception:
        return default
