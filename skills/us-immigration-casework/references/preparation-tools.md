# v1.2 local command contract

Resolve the installed skill directory, copy blank assets to a private case workspace, and fill them only with supplied or verified facts. All JSON inputs reject duplicate keys and nonfinite values. Inputs are limited to 10 MB; CLI errors omit private values. A zero exit code means a command ran, not that a legal application is valid. Review-required findings are in JSON, with exit code 0; malformed inputs, unavailable dependencies and output collisions return 2.

```bash
python3 "$SKILL_ROOT/scripts/preparation.py" ds160 --input /private/case/ds160.json --as-of 2026-10-31
python3 "$SKILL_ROOT/scripts/preparation.py" refusal --input /private/case/refusal.json
python3 "$SKILL_ROOT/scripts/document_ocr.py" --input /private/case/notice.pdf --out /private/case/ocr-001 --document-id E001 --language eng
python3 "$SKILL_ROOT/scripts/preparation.py" export --input /private/case/packet.json --out /private/case/export-001
python3 "$SKILL_ROOT/scripts/preparation.py" export --input /private/case/packet.json --out /private/case/export-002 --formats md html json pdf docx --attach /private/case/notice.pdf
```

`ds160-1.0` requires `fields` rows with value, one evidence status, applicant confirmation and optional explanation/not_applicable/evidence. Each document-verified row needs `evidence: [{"document_id":"E001","page":1}]`; the script validates pointer shape, not the document's existence or authenticity. `prior_refusal` and `immigrant_petition` require actual booleans; true values need an explanation. The 23 baseline topics are selected preparation checks, not a live CEAC schema. Add conditional questions and individually review all security questions with the applicant. The tool never signs, submits or calculates approval probability.

`refusal-1.0` accepts an array of exact grounds plus `notice` document ID, positive page number and explicit human_reviewed boolean. Unknown/mixed grounds remain visible as specialist routes; OCR-only or missing notice inspection remains unverified. No inferred appeal, waiver or deadline is created.

`packet-1.0` requires case_id (letters/digits/underscore/hyphen, max 64), title (max 200), language and nonempty sections of heading/body plain text. Sections are curated by the host; raw worksheets and internal findings are not automatically merged. `ocr-1.0` preserves source hash and page/token provenance. See the dedicated workflows before use; evidence and legal review cannot be replaced by schema validation.
