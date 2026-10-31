# Output contract and local tools

## Case manifest

Use `assets/case.schema.json` and `casework.py init`. Schema version `1.0` contains case_id, language, process, stage, facts, events, evidence, sources, deadlines, actions. Store necessary identifiers as facts; credentials nowhere.

Link records by IDs without repeating private contents. A source contains ID, kind (`official_web`, `notice`, `user_statement`, `other`), title, optional URL/checked date/evidence ID. Evidence has ID, label, optional private path. `document_verified` facts/events require a notice or official-web source. Inferred facts need sources and explanation. The linkage is not forensic authentication.

Events have ID, kind, ISO date, status, source_ids. Kinds: `uscis_received`, `uscis_approved`, `nvc_created`, `nvc_dq`, `interview_scheduled`, `interview_taken`, `visa_issued`, `us_admitted`, `other`. Record a future appointment as scheduled, not completed.

Deadlines have ID, ISO date, IANA time zone, action, delivery_rule, source_id. This records a sourced due date; it does not calculate legal service rules. Put unresolved dates/conditions into actions and narrative, not invented deadline fields.

Actions have ID, description, state (`draft`, `review_required`, `ready_for_signature`, `submitted`, `blocked`), source_ids. Submitted actions additionally need submission_evidence_id linking existing evidence. The CLI checks the link, not actual transmission.

## Commands

| Command | Result | Limit |
| --- | --- | --- |
| `init --out DIR --case-id ID --language en/es` | Private case.json/report/CSV ledgers/.gitignore | Refuses existing output, symlink paths, Git workspaces |
| `wait --received DATE --as-of DATE` | JSON days/calendar months/remainder | No legal deadline or forecast |
| `audit --case FILE` | JSON structural errors/selected consistency warnings | No legal sufficiency/authenticity certification |
| `source --url URL` | Host/origin/allowlist classification | No fetch/content/freshness verification |
| `redact --input FILE --output FILE` | New redacted UTF-8 file, or stdin/stdout when omitted | Best effort; manual privacy review required |

Exit status: 0 success/no audit findings; 1 audit findings or non-allowlisted source; 2 invalid input/operational error. Audit reports field paths/codes without echoing case values. Dates are strict YYYY-MM-DD. Helpers submit nothing and do not silently overwrite outputs. POSIX directories/files receive restricted permissions; Windows permissions/encryption need separate management.

## Report

Use the case-report template for full assessments. Keep labels visible; distinguish supplied data, inspected results, interpretation, estimates. Include the timestamp of live checks. Scale down for small questions.

Retain sources separately from conclusions: supported claim, section/page, accessed/effective dates, retrieval method. CSV templates start with headers, not private sample data.

A clean audit is not exhaustive: manually evaluate parallel proceedings, source contents/freshness, authority, causation, eligibility, time-zone validity, and submission conditions with the host and appropriate professional. Stage progression and chronology warnings apply to a single consular route; they do not treat an adjustment interview as a consular event.
