#!/usr/bin/env python3
"""Local case-file helpers. No network, legal decisions, or filing automation."""
from __future__ import annotations

import argparse
import calendar
import json
import os
from pathlib import Path
import re
import shutil
import sys
from datetime import date
from urllib.parse import urlsplit

VERSION = "1.0.0"
SKILL_ROOT = Path(__file__).resolve().parents[1]
STATUSES = {"document_verified", "user_reported", "inferred", "unverified", "contradicted"}
OFFICIAL_DOMAINS = (
    "uscis.gov", "state.gov", "justice.gov", "ecfr.gov", "house.gov",
    "senate.gov", "uscourts.gov", "usembassy.gov", "govinfo.gov",
    "cbp.gov", "ice.gov", "dhs.gov", "federalregister.gov",
)
STAGE_RANK = {
    "uscis_pending": 0, "uscis_approved": 1, "nvc_pending": 2,
    "nvc_dq": 3, "interview_scheduled": 4, "consular_review": 5,
    "visa_issued": 6, "admitted": 7,
}
EVENT_RANK = {
    "uscis_received": 0, "uscis_approved": 1, "nvc_created": 2,
    "nvc_dq": 3, "interview_scheduled": 4, "interview_taken": 5,
    "visa_issued": 6, "us_admitted": 7,
}


def parse_date(value: str) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Use a valid date in YYYY-MM-DD format.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Use a valid date in YYYY-MM-DD format.") from exc


def elapsed(received: str, as_of: str) -> dict:
    start, end = parse_date(received), parse_date(as_of)
    if end < start:
        raise ValueError("Analysis date must not precede receipt date.")
    months = (end.year - start.year) * 12 + end.month - start.month

    def anniversary(offset: int) -> date:
        year, month0 = divmod(start.year * 12 + start.month - 1 + offset, 12)
        month = month0 + 1
        return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))

    if anniversary(months) > end:
        months -= 1
    return {
        "received": start.isoformat(), "as_of": end.isoformat(),
        "elapsed_days": (end - start).days, "calendar_months": months,
        "remaining_days": (end - anniversary(months)).days,
        "method": "clamped_monthly_anniversary",
        "legal_deadline_calculated": False, "approval_forecast": None,
    }


def classify_source(url: str) -> dict:
    """Classify a host, without fetching or returning URL queries/fragments."""
    invalid = {"official_domain_candidate": False, "host": None,
               "origin": None, "page_fetched": False, "reason": "invalid_or_unsafe_url"}
    if not isinstance(url, str) or len(url) > 8192 or any(c.isspace() for c in url):
        return invalid
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        port = parsed.port
        if (parsed.scheme != "https" or parsed.username is not None
                or parsed.password is not None or port not in (None, 443)
                or not host or ".." in host or not host.isascii()):
            return invalid
        host = host.removesuffix(".")
        allowed = any(host == d or host.endswith("." + d) for d in OFFICIAL_DOMAINS)
        return {"official_domain_candidate": allowed, "host": host,
                "origin": "https://" + host, "page_fetched": False,
                "reason": "allowlisted_host" if allowed else "host_not_allowlisted"}
    except ValueError:
        return invalid


def load_json(path: Path) -> object:
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("JSON input exceeds the 8 MiB limit.")
    try:
        def unique_pairs(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("JSON input contains duplicate object keys.")
                result[key] = value
            return result
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Non-finite JSON number.")))
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError("Input must be valid UTF-8 JSON.") from exc


def schema_errors(value: object, schema: dict, root: dict, path: str = "$") -> list:
    """Validate the deliberately small subset used by the bundled JSON schema."""
    if "$ref" in schema:
        target = root
        for part in schema["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        return schema_errors(value, target, root, path)
    errors = []
    types = schema.get("type", [])
    types = [types] if isinstance(types, str) else types
    matches = {
        "object": isinstance(value, dict), "array": isinstance(value, list),
        "string": isinstance(value, str), "null": value is None,
        "boolean": isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
    }
    if types and not any(matches[t] for t in types):
        return [{"path": path, "code": "wrong_type", "severity": "error"}]
    if "const" in schema and value != schema["const"]:
        errors.append({"path": path, "code": "unexpected_value", "severity": "error"})
    if "enum" in schema and value not in schema["enum"]:
        errors.append({"path": path, "code": "unexpected_value", "severity": "error"})
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append({"path": path, "code": "empty_string", "severity": "error"})
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append({"path": path, "code": "invalid_format", "severity": "error"})
        if schema.get("format") == "date":
            try:
                parse_date(value)
            except ValueError:
                errors.append({"path": path, "code": "invalid_date", "severity": "error"})
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append({"path": path + "." + key, "code": "required_field", "severity": "error"})
        for key, item in value.items():
            if key in props:
                errors.extend(schema_errors(item, props[key], root, path + "." + key))
            elif schema.get("additionalProperties") is False:
                # Do not echo an unknown key; it could contain private information.
                errors.append({"path": path, "code": "unknown_field", "severity": "error"})
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            errors.extend(schema_errors(item, schema["items"], root, f"{path}[{i}]"))
    return errors


def audit(case: object, as_of: str | None = None) -> dict:
    schema = load_json(SKILL_ROOT / "assets" / "case.schema.json")
    issues = schema_errors(case, schema, schema)
    result = {"schema_version": "1.0", "issues": issues,
              "legal_sufficiency_checked": False, "documents_authenticated": False}
    if issues:
        result["valid_structure"] = False
        return result
    indexes = {}

    def add(path: str, code: str, severity: str = "error"):
        issues.append({"path": path, "code": code, "severity": severity})

    for group in ("facts", "events", "evidence", "sources", "deadlines", "actions"):
        indexes[group] = {}
        for i, row in enumerate(case[group]):
            if row["id"] in indexes[group]:
                add(f"$.{group}[{i}].id", "duplicate_id")
            indexes[group][row["id"]] = row
    for i, source in enumerate(case["sources"]):
        if source.get("evidence_id") and source["evidence_id"] not in indexes["evidence"]:
            add(f"$.sources[{i}].evidence_id", "missing_evidence_reference")
        if source["kind"] == "notice" and not source.get("evidence_id"):
            add(f"$.sources[{i}]", "notice_requires_evidence")
        if source["kind"] == "official_web":
            if not source.get("url"):
                add(f"$.sources[{i}].url", "official_web_requires_url")
            elif not classify_source(source["url"])["official_domain_candidate"]:
                add(f"$.sources[{i}].url", "source_domain_needs_review", "warning")
    for group in ("facts", "events", "actions"):
        for i, row in enumerate(case[group]):
            base = f"$.{group}[{i}]"
            linked = []
            for j, sid in enumerate(row["source_ids"]):
                if sid not in indexes["sources"]:
                    add(base + f".source_ids[{j}]", "missing_source_reference")
                else:
                    linked.append(indexes["sources"][sid])
            if row.get("status") == "document_verified":
                usable = [s for s in linked if s["kind"] in {"notice", "official_web"}
                          and s["access_method"] in {"direct", "user_copy"} and s.get("checked_at")]
                if not usable:
                    add(base, "verified_claim_requires_inspected_source")
            if row.get("status") == "inferred" and (not linked or not row.get("explanation")):
                add(base, "inference_requires_sources_and_explanation")
            if row.get("status") == "contradicted":
                add(base, "unresolved_contradiction", "warning")
            if group == "actions" and row["state"] == "submitted":
                if row.get("submission_evidence_id") not in indexes["evidence"]:
                    add(base, "submission_requires_evidence")
    for i, deadline in enumerate(case["deadlines"]):
        if deadline["source_id"] not in indexes["sources"]:
            add(f"$.deadlines[{i}].source_id", "deadline_requires_source")
        elif indexes["sources"][deadline["source_id"]]["kind"] not in {"notice", "official_web"}:
            add(f"$.deadlines[{i}].source_id", "deadline_requires_primary_basis")
        elif not indexes["sources"][deadline["source_id"]].get("checked_at") or indexes["sources"][deadline["source_id"]]["access_method"] not in {"direct", "user_copy"}:
            add(f"$.deadlines[{i}].source_id", "deadline_basis_not_inspected")
    completed = []
    day = parse_date(as_of) if as_of else None
    for i, event in enumerate(case["events"]):
        if event["status"] not in {"document_verified", "user_reported"}:
            continue
        kind = event["kind"]
        if kind not in EVENT_RANK:
            continue
        if case["process"] == "consular" and case["stage"] in STAGE_RANK and EVENT_RANK[kind] > STAGE_RANK[case["stage"]]:
            add(f"$.events[{i}]", "stage_event_conflict", "warning")
        if kind != "interview_scheduled":
            completed.append((i, EVENT_RANK[kind], parse_date(event["date"])))
            if day and parse_date(event["date"]) > day:
                add(f"$.events[{i}].date", "completed_event_in_future", "warning")
    for index, rank, event_day in completed:
        if case["process"] == "consular" and any(other_rank < rank and other_day > event_day
               for _, other_rank, other_day in completed):
            add(f"$.events[{index}].date", "chronology_conflict", "warning")
    result["valid_structure"] = not any(i["severity"] == "error" for i in issues)
    return result


def reject_symlink_path(path: Path) -> None:
    absolute = path.expanduser().absolute()
    for part in (absolute, *absolute.parents):
        if part.is_symlink():
            raise ValueError("Refusing a path containing a symbolic link.")


def private_write(path: Path, text: str) -> None:
    reject_symlink_path(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def blank_case(case_id: str, language: str) -> dict:
    return {"schema_version": "1.0", "case_id": case_id, "language": language,
            "process": "unknown", "stage": "unknown", "facts": [], "events": [],
            "evidence": [], "sources": [], "deadlines": [], "actions": []}


def init_workspace(out: Path, case_id: str, language: str) -> dict:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,47}", case_id):
        raise ValueError("Case ID must use 1-48 lowercase letters, numbers, or hyphens.")
    if language not in {"en", "es"}:
        raise ValueError("Supported languages: en, es.")
    out = out.expanduser().absolute()
    reject_symlink_path(out)
    if any((p / ".git").exists() for p in (out, *out.parents)):
        raise ValueError("Create private case files outside Git workspaces.")
    if out.exists():
        raise ValueError("Output already exists; no files were overwritten.")
    out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    out.mkdir(mode=0o700, exist_ok=False)
    try:
        private_write(out / "case.json", json.dumps(blank_case(case_id, language), indent=2) + "\n")
        private_write(out / ".gitignore", "*\n!.gitignore\n")
        for name in ("case-report.md", "evidence.csv", "sources.csv", "actions.csv", "form-map.csv"):
            private_write(out / name, (SKILL_ROOT / "assets" / "templates" / name).read_text(encoding="utf-8"))
    except Exception:
        shutil.rmtree(out)
        raise
    return {"created": True, "files": 7, "network_used": False,
            "case_content_initialized": False, "language": language}


REDACTIONS = (
    (re.compile(r"\b(?:IOE|EAC|WAC|LIN|SRC|MSC|NBC|YSC)\d{10}\b", re.I), "[RECEIPT]"),
    (re.compile(r"\bA[- ]?\d{7,9}\b", re.I), "[A-NUMBER]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),
    (re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+", re.I), "[EMAIL]"),
    (re.compile(r"(?<!\w)(?:\+?1[ .-]?)?(?:\(\d{3}\)|\d{3})[ .-]?\d{3}[ .-]?\d{4}(?!\w)"), "[PHONE]"),
)


def redact(text: str) -> str:
    for pattern, replacement in REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=VERSION)
    commands = parser.add_subparsers(dest="command", required=True)
    wait = commands.add_parser("wait", help="Elapsed calendar time, not a legal deadline")
    wait.add_argument("--received", required=True)
    wait.add_argument("--as-of", required=True)
    init = commands.add_parser("init", help="Create a new private case workspace")
    init.add_argument("--out", type=Path, required=True)
    init.add_argument("--case-id", required=True)
    init.add_argument("--language", choices=("en", "es"), default="en")
    check = commands.add_parser("audit", help="Check structure and selected consistency rules")
    check.add_argument("--case", type=Path, required=True)
    check.add_argument("--as-of", help="Optional date for future-completed-event checks")
    source = commands.add_parser("source", help="Classify a URL host without fetching it")
    source.add_argument("--url", required=True)
    masking = commands.add_parser("redact", help="Best-effort text redaction; review manually")
    masking.add_argument("--input", type=Path)
    masking.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        status = 0
        if args.command == "wait":
            result = elapsed(args.received, args.as_of)
        elif args.command == "init":
            result = init_workspace(args.out, args.case_id, args.language)
        elif args.command == "audit":
            result = audit(load_json(args.case), args.as_of)
            status = 1 if result["issues"] else 0
        elif args.command == "source":
            result = classify_source(args.url)
            status = 0 if result["official_domain_candidate"] else 1
        else:
            original = args.input.read_text(encoding="utf-8") if args.input else sys.stdin.read()
            output = redact(original)
            if args.output:
                private_write(args.output, output)
            else:
                sys.stdout.write(output)
            print("Best-effort text redaction only. Manually review names, addresses, health details, images and metadata before sharing.", file=sys.stderr)
            return 0
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return status
    except (ValueError, OSError, UnicodeError) as exc:
        message = str(exc) if isinstance(exc, ValueError) and not isinstance(exc, UnicodeError) else "Unable to read or write the requested path."
        print("Error: " + message, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
