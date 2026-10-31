#!/usr/bin/env python3
"""Offline metadata, relative-link, version, and selected disclosure checks."""
from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "us-immigration-casework"
EXCLUDED = {".git", "__pycache__", ".venv", "build", "dist"}


def check(root: Path = ROOT) -> list[str]:
    problems = []
    skill = root / "skills" / "us-immigration-casework"
    required = ["README.md", "README.es.md", "LICENSE", "VERSION", "SECURITY.md", "CONTRIBUTING.md",
                "skills/us-immigration-casework/SKILL.md", "skills/us-immigration-casework/assets/case.schema.json",
                "skills/us-immigration-casework/agents/openai.yaml", ".github/workflows/ci.yml"]
    for name in required:
        if not (root / name).is_file(): problems.append("missing required file: " + name)
    if not (skill / "SKILL.md").exists(): return problems
    manifest = (skill / "SKILL.md").read_text(encoding="utf-8")
    front = re.match(r"\A---\n(.*?)\n---\n", manifest, re.S)
    if front is None:
        problems.append("SKILL.md requires YAML frontmatter")
    else:
        keys = re.findall(r"^([a-z_-]+):", front.group(1), re.M)
        if keys != ["name", "description"]: problems.append("portable frontmatter must contain name and description")
        if "name: us-immigration-casework\n" not in front.group(1) + "\n": problems.append("unexpected skill name")
    if len(manifest.splitlines()) >= 500: problems.append("SKILL.md must remain below 500 lines")
    version = (root / "VERSION").read_text().strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version): problems.append("VERSION must be semantic version")
    for name in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json"):
        data = json.loads((root / name).read_text())
        if data["version"] != version: problems.append("version mismatch: " + name)
    tree = ast.parse((skill / "scripts" / "casework.py").read_text())
    cli_versions = [node.value.value for node in tree.body if isinstance(node, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "VERSION" for t in node.targets)
                    and isinstance(node.value, ast.Constant)]
    if cli_versions != [version]: problems.append("CLI version mismatch")
    schema = json.loads((skill / "assets" / "case.schema.json").read_text())
    if schema.get("properties", {}).get("schema_version", {}).get("const") != "1.0":
        problems.append("unexpected case schema version")
    for file in root.rglob("*"):
        relative = file.relative_to(root)
        if any(part in EXCLUDED for part in relative.parts): continue
        if file.is_symlink():
            problems.append("symbolic link is not allowed in publication: " + relative.as_posix())
            continue
        if not file.is_file(): continue
        if file.suffix.lower() not in {".md", ".py", ".json", ".jsonl", ".yml", ".yaml", ".svg", ".csv", ".txt"}:
            continue
        text = file.read_text(encoding="utf-8")
        checks = [
            (r"\b(?:IOE|EAC|WAC|LIN|SRC|MSC|NBC|YSC)(?!0{10}\b)\d{10}\b", "possible real receipt identifier"),
            (r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", "private key"),
            (r"\bgh[pousr]_[A-Za-z0-9]{24,}\b", "GitHub token"),
            (r"\b\d{6,12}:[A-Za-z0-9_-]{30,}\b", "Telegram bot token"),
            (r"\bsk-proj-[A-Za-z0-9_-]{24,}\b", "API key"),
        ]
        for pattern, label in checks:
            if re.search(pattern, text): problems.append(label + " in " + relative.as_posix())
        if file.suffix == ".md":
            for target in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", text):
                target = target.split("#", 1)[0]
                if not target or re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", target): continue
                if not (file.parent / target).exists():
                    problems.append("broken relative link in " + relative.as_posix() + ": " + target)
    return problems


def main() -> int:
    try:
        problems = check()
    except (OSError, ValueError, KeyError, SyntaxError):
        print("Package check could not read a required file or metadata structure.", file=sys.stderr)
        return 2
    if problems:
        for problem in problems: print(problem, file=sys.stderr)
        return 1
    print("Package metadata, relative links, versions and selected disclosure checks passed.")
    print("This is not exhaustive secret detection or legal/content validation.")
    return 0


if __name__ == "__main__": raise SystemExit(main())
