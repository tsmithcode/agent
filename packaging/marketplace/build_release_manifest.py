from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _collect_artifacts(dist_dir: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in sorted(dist_dir.glob("*")):
        if not p.is_file():
            continue
        out.append(
            {
                "file": p.name,
                "bytes": p.stat().st_size,
                "sha256": _sha256(p),
            }
        )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate marketplace release manifest from base app manifest and build artifacts."
    )
    parser.add_argument(
        "--base-manifest",
        default="packaging/marketplace/app-manifest.json",
        help="Path to base app manifest JSON.",
    )
    parser.add_argument("--dist-dir", default="dist", help="Distribution directory containing built artifacts.")
    parser.add_argument(
        "--out-dir",
        default="packaging/marketplace/dist",
        help="Output directory for generated release manifest files.",
    )
    parser.add_argument(
        "--release-ref",
        default="",
        help="Release reference (e.g., refs/tags/v1.2.3 or commit SHA).",
    )
    args = parser.parse_args()

    base_manifest_path = Path(args.base_manifest).resolve()
    dist_dir = Path(args.dist_dir).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    base = _load_json(base_manifest_path)
    artifacts = _collect_artifacts(dist_dir)

    release_manifest = dict(base)
    release_manifest["release"] = {
        "generated_ts_utc": datetime.now(timezone.utc).isoformat(),
        "release_ref": args.release_ref,
        "artifacts": artifacts,
    }

    (out_dir / "app-manifest.json").write_text(
        json.dumps(base, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    (out_dir / "app-manifest.release.json").write_text(
        json.dumps(release_manifest, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
