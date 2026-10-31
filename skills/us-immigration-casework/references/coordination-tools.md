# v2.0 command contract

Python 3.10+ core uses standard-library JSON, SQLite, datetime and zoneinfo. Timezone databases may require optional `tzdata`, especially on Windows. The existing v1.x case manifests/helpers remain supported; v2.0 adds separate event/coordination schemas without migrating existing case files. No existing case is automatically enrolled, uploaded or scheduled.

```bash
python3 "$SKILL_ROOT/scripts/agenda.py" --input /private/case/calendar-events.json --out /private/case/calendar-001 --generated-at 2026-10-31T15:00:00Z
python3 "$SKILL_ROOT/scripts/coordination.py" init --out /private/case/team --owner case-owner --now 2026-10-31T15:00:00Z
python3 "$SKILL_ROOT/scripts/coordination.py" apply --db /private/case/team/coordination.sqlite3 --input /private/case/operation.json --now 2026-10-31T15:00:00Z
python3 "$SKILL_ROOT/scripts/coordination.py" status --db /private/case/team/coordination.sqlite3 --now 2026-10-31T15:00:00Z
python3 "$SKILL_ROOT/scripts/coordination.py" snapshot --db /private/case/team/coordination.sqlite3 --out /private/case/team-snapshot-001 --now 2026-10-31T15:00:00Z
```

Use the actual current clock; example timestamps are not authorization. JSON loader rejects duplicate keys, nonfinite numbers and inputs above 10 MB. CLI errors omit private values and exit 2. Success means a local operation completed, not an external service effect. `status` is a one-time query, not a scheduler. Snapshot exports contain private case workflow data and are not public audit reports.

Every operation has `actor`, `expected_revision` and `operation`; all except connector.configure need case_id. IDs use letters/digits/underscore/hyphen, max 64. Init starts revision 0. Every accepted operation, including a duplicate prepare, advances the ledger revision. Do not replay a saved expected_revision blindly.

| Operation | Additional fields |
| --- | --- |
| case.create | New case_id; ledger owner only |
| member.add / member.remove | member; add also requires role owner/preparer/reviewer/observer; removal cannot remove owners |
| artifact.revise | artifact_id, sha256 of actual file |
| review.assign | artifact_id, current artifact_revision, sha256, reviewer |
| review.decide | artifact_id, current artifact_revision, sha256, decision approved/changes_requested, note |
| task.create | task_id, assignee, summary |
| task.transition | task_id, status todo/in_progress/blocked/done |
| connector.configure | provider, enabled boolean, account_ref; ledger owner only |
| action.prepare | request_id, provider, provider_operation, account_ref, destination, not_before offset timestamp, data |
| action.authorize | request_id, request_hash from prepare, authorization_ref identifying actual user instruction, expires_at |
| action.revoke | request_id |
| action.claim | request_id, observed_capabilities map; CLI also requires --bridge-out new private folder |
| action.preflight | request_id, attempt_id; recheck immediately before the host call |
| action.receipt | request_id, attempt_id, request_hash, outcome confirmed/not_applied/unknown, result_ref; confirmed also needs external_id |
| action.retry | request_id; owner only after verified not_applied; clears old authorization |

Operation-specific `data`: calendar.create uses event-2.0; notification.draft/send uses to, recipient_verified, verification_ref, subject, body and send requires actual saved draft_id; reminder.schedule uses when and message. Destination names the exact calendar/mailbox/self target, and account_ref names the exact authorized account. Notification adapters never add attachments, cc or bcc. The host must verify all mapped fields and the actual saved draft before send. An existing draft ID alone is insufficient evidence of unchanged contents.

The request_hash binds case, provider, operation, account, destination, not_before and the generated payload. Content cannot be edited in place: use a new request ID and authorization. Exact repeats under the same request ID are deduplicated; equivalent payloads under a different ID are rejected. The host must still search for prior effects, especially for updated event revisions and requests created with changed timing. No exactly-once guarantee spans a local transaction and an external API.

Claim exports a bridge request to a private file and atomically marks dispatching. If writing the bridge file fails, the claim remains dispatching: inspect the ledger and reconcile, never requeue blindly. An unavailable capability fails before claiming. Provider mapping uses the current host tool schema; there are no executable hooks or credential fields. The local bridge is an attestation contract, not permission to bypass host policy. No real provider task/mail/event is created by these scripts.

Compatibility: all three agent hosts can use the local CLI/Markdown workflows; connectors run only where a compatible authenticated tool and scheduler are actually available. Model-host live integration is not exercised by the deterministic suite. Tests use synthetic payloads, a temporary SQLite ledger and mock capability observations; they do not create live mail, meetings or notifications.
