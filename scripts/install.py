#!/usr/bin/env python3
"""Install the portable skill by copying reviewed local files. No network."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from uuid import uuid4

NAME = "us-immigration-casework"
ROOT = Path(__file__).resolve().parents[1]


def reject_symlinks(path: Path) -> None:
    for item in (path.absolute(), *path.absolute().parents):
        if item.is_symlink():
            raise ValueError("Refusing a destination containing symbolic links.")


def destination(target: str, scope: str, project_root: Path | None = None,
                user_home: Path | None = None) -> Path:
    if target not in {"codex", "claude", "deepseek"} or scope not in {"user", "project"}:
        raise ValueError("Unknown install target or scope.")
    base = project_root if scope == "project" else (user_home or Path.home())
    if base is None:
        raise ValueError("Project scope requires an explicit project root.")
    folder = {"codex": ".agents", "claude": ".claude", "deepseek": ".dsh"}[target]
    if target == "deepseek" and scope == "user" and os.environ.get("DSH_HOME"):
        base = Path(os.environ["DSH_HOME"]).expanduser()
        if not base.is_absolute():
            raise ValueError("DSH_HOME must be absolute.")
        return base / "skills" / NAME
    return base.expanduser().absolute() / folder / "skills" / NAME


def fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    for file in sorted(root.rglob("*")):
        if "__pycache__" in file.relative_to(root).parts or file.suffix == ".pyc" or file.name == ".DS_Store":
            continue
        if file.is_symlink():
            raise ValueError("Source bundles must not contain symbolic links.")
        if not file.is_file():
            continue
        digest.update(file.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(file.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def install(source: Path, dest: Path, replace: bool = False, dry_run: bool = False) -> dict:
    if not (source / "SKILL.md").is_file():
        raise ValueError("Source skill is missing SKILL.md.")
    if source.is_symlink() or any(p.is_symlink() for p in source.rglob("*")):
        raise ValueError("Source bundles must not contain symbolic links.")
    reject_symlinks(dest)
    source = source.resolve()
    dest = dest.expanduser().absolute()
    if source == dest.resolve() or source in dest.resolve().parents or dest.resolve() in source.parents:
        raise ValueError("Source and destination must not overlap.")
    if dest.exists() and not dest.is_dir():
        raise ValueError("Destination exists and is not a directory.")
    source_hash = fingerprint(source)
    if dest.exists() and fingerprint(dest) == source_hash:
        return {"state": "unchanged", "destination": str(dest), "sha256": source_hash}
    if dest.exists() and not replace:
        raise ValueError("Destination differs; use --replace to retain a backup and install the reviewed version.")
    if dry_run:
        return {"state": "planned", "destination": str(dest), "sha256": source_hash,
                "existing_copy_will_be_backed_up": dest.exists()}
    dest.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".casework-install-", dir=dest.parent))
    backup = None
    try:
        shutil.copytree(source, staging / NAME, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
        if fingerprint(staging / NAME) != source_hash:
            raise ValueError("Copied bundle did not match the source.")
        if dest.exists():
            # A sibling outside the scanner root avoids duplicate catalog entries.
            backup_root = dest.parent.parent / "casework-backups"
            reject_symlinks(backup_root)
            backup_root.mkdir(exist_ok=True)
            backup = backup_root / (NAME + "-" + uuid4().hex)
            dest.rename(backup)
        try:
            (staging / NAME).rename(dest)
        except Exception:
            if backup is not None and not dest.exists():
                backup.rename(dest)
            raise
    finally:
        shutil.rmtree(staging)
    return {"state": "installed", "destination": str(dest), "sha256": source_hash,
            "backup": str(backup) if backup else None, "network_used": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("codex", "claude", "deepseek", "all"), required=True)
    parser.add_argument("--scope", choices=("user", "project"), default="user")
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--replace", action="store_true", help="Keep an existing different copy in a backup folder")
    args = parser.parse_args(argv)
    if (args.scope == "project") != (args.project_root is not None):
        parser.error("Use --project-root exactly when --scope project is selected.")
    targets = ("codex", "claude", "deepseek") if args.target == "all" else (args.target,)
    source = ROOT / "skills" / NAME
    try:
        # Preflight every destination before mutating any of them.
        paths = [destination(t, args.scope, args.project_root) for t in targets]
        for path in paths:
            install(source, path, args.replace, dry_run=True)
        results = [install(source, path, args.replace, dry_run=args.dry_run) for path in paths]
        print(json.dumps({"results": results}, indent=2))
        return 0
    except (ValueError, OSError) as exc:
        message = str(exc) if isinstance(exc, ValueError) else "Unable to complete the local file operation."
        print("Error: " + message, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
