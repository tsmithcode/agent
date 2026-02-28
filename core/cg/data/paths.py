from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    home: Path
    agent_root: Path
    workspace: Path
    host_ai: Path
    memory_root: Path
    chroma_dir: Path
    logs_dir: Path
    artifacts_dir: Path

    @staticmethod
    def _env_path(name: str) -> Path | None:
        v = (os.getenv(name) or "").strip()
        if not v:
            return None
        return Path(os.path.expanduser(v)).resolve()

    @staticmethod
    def _is_under(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except Exception:
            return False

    @staticmethod
    def _is_shared_host_ai(host_ai: Path) -> bool:
        """
        Heuristic: host_ai is considered "shared" if:
        - it's a symlink, OR
        - it resolves under /mnt/hgfs (VMware Shared Folders)
        """
        try:
            if host_ai.is_symlink():
                return True
        except Exception:
            pass
        try:
            resolved = host_ai.resolve()
            return str(resolved).startswith("/mnt/hgfs/")
        except Exception:
            return False

    @staticmethod
    def resolve() -> "Paths":
        home = Paths._env_path("CG_HOME") or Path(os.path.expanduser("~")).resolve()
        if str(home) == "/":
            raise RuntimeError("Refusing to run with home='/' (unexpected HOME resolution).")

        agent_root = Paths._env_path("CG_AGENT_ROOT") or (home / "agent").resolve()
        workspace = Paths._env_path("CG_WORKSPACE") or (agent_root / "workspace").resolve()

        host_ai = Paths._env_path("CG_HOST_AI") or (home / "host_ai").resolve()
        memory_root = (host_ai / "memory").resolve()
        chroma_dir = (memory_root / "chroma").resolve()
        logs_dir = (host_ai / "logs").resolve()
        artifacts_dir = (host_ai / "artifacts").resolve()

        # Safety checks: keep critical roots sane
        if not Paths._is_under(agent_root, home):
            raise RuntimeError(f"agent_root must be under home. agent_root={agent_root} home={home}")
        if not Paths._is_under(workspace, agent_root):
            raise RuntimeError(f"workspace must be under agent_root. workspace={workspace} agent_root={agent_root}")

        # Ensure dirs exist
        for d in [workspace, memory_root, chroma_dir, logs_dir, artifacts_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # Snapshot-size / persistence warning if host_ai isn't shared-backed
        # (Do not hard-fail; allow local-only mode.)
        if not Paths._is_shared_host_ai(host_ai):
            warn_file = logs_dir / "WARN_HOST_AI_NOT_SHARED.txt"
            if not warn_file.exists():
                warn_file.write_text(
                    "WARNING: ~/host_ai does not appear to be a VMware shared folder (/mnt/hgfs) or a symlink.\n"
                    "This may increase VM snapshot size because memory/logs/artifacts will live on the VM disk.\n"
                    "Recommended: symlink ~/host_ai -> /mnt/hgfs/<YOUR_SHARED_FOLDER>/host_ai\n",
                    encoding="utf-8",
                )

        return Paths(
            home=home,
            agent_root=agent_root,
            workspace=workspace,
            host_ai=host_ai,
            memory_root=memory_root,
            chroma_dir=chroma_dir,
            logs_dir=logs_dir,
            artifacts_dir=artifacts_dir,
        )