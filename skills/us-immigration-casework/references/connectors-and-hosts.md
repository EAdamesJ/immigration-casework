# Optional connectors and host execution

This skill is portable workflow code, not an OAuth client, background server or bundled MCP service. All connectors start unconfigured/disabled. Core operations and ICS exports run offline. `scripts/connectors.py` builds adapter payloads; `scripts/coordination.py` binds them to an authorized queue entry and exports a bridge request. A live tool-enabled host performs the actual operation with its own authentication, permissions, confirmation policy and readback. A prepared JSON file or enabled flag proves no live account access.

| Adapter | Implemented operation | Host route |
| --- | --- | --- |
| google_calendar | calendar.create | Discover Google Calendar create/read/search tools; map payload fields against current tool schema |
| outlook_calendar | calendar.create, timed only, one alarm | Discover Outlook Calendar or a configured Microsoft Graph/MCP tool; not the Outlook email connector |
| gmail | notification.draft, notification.send existing draft | Resolve recipient, create draft; reread the actual saved draft before an authorized send |
| outlook_mail | notification.draft, notification.send existing draft | Discover Outlook draft/send/read operations and verify actual stored contents |
| host_automation | reminder.schedule, one-time, self | Discover an actual scheduler, create the task, then record returned ID/status |

These are adapter payloads, not arguments to paste blindly into an MCP tool. Google REST/Graph field names differ from host wrappers. Do not silently drop privacy flags, calendar IDs, recipients, alarm settings or account constraints. If a required field cannot be mapped, keep the action blocked and offer ICS/local draft fallback. Outlook all-day events and multiple Outlook reminders are deliberately unsupported by the adapter. Google event ID and Outlook transactionId support reconciliation; they do not replace lookup/readback. Existing events require a separately authorized host update workflow; do not create a second event to apply a revision.

Discover capabilities at use; fill `assets/connector-capabilities.json` only from observed tools and their actual support. Missing tools, 401/403, revoked access and expired credentials remain access problems. Never treat them as immigration decisions or bypass through scraped government portals. Request installation/authentication only for a task needing that service, through the host's supported secure flow. Never collect passwords, security answers, cookies, API keys or OAuth tokens in case files or source control.

Before a write, verify exact account and destination, case authority, recipient identity, purpose, content, data disclosure, attachments and prior user authorization. Live external actions must satisfy the host's policy independently of the local ledger. The build request authorizes software development only; do not create test meetings, send real mail, grant real folder access or schedule sample notifications. Existing authorization that clearly covers the exact action remains sufficient; do not ask again merely because a local reference must be recorded.

Dispatch protocol:

1. Prepare the concrete action and read its request_hash. Configure the provider/account deliberately; scopes remain the host's responsibility.
2. Record the actual user's authorization reference, bound hash and explicit expiry. Local `action.authorize` records an attestation; it does not itself obtain consent or authenticate an actor.
3. Before claim, resolve the recipient (email syntax alone is not identity verification), discover the exact tool, inspect duplicates and compare current target/content. Use an actual current clock for `--now`, not a saved sample time.
4. Claim once with the observed capability map and a new private bridge output folder. The atomic ledger marks `dispatching` before any live call. Review the bridge contents and run action.preflight immediately before the live call to recheck expiry, revocation and account. There is still no atomic transaction with the external provider. Perform only the described action through the authorized host connector. Keep account/destination constraints exact.
5. For email send, reread the saved draft; compare to, cc, bcc, subject, body and attachments to the authorized payload. This adapter supports one recipient, no cc/bcc or attachments. Any mismatch requires a new prepared action/authorization; never send a changed draft under an old hash.
6. Read back actual provider state. Record attempt_id, request_hash, result_ref and provider ID. `confirmed` means the provider effect was observed/accepted, not email delivery or human acknowledgment. A mail draft is not sent; a scheduler task is not yet fired.
7. A timeout or crash after claim is `dispatching`/`unknown`; never retry automatically. Search the actual destination and reconcile. Only a documented `not_applied` result permits owner-initiated retry, which clears authorization and requires the host to check current authorization again. Preserve the old audit trail. Local revocation does not cancel an already executed action or provider task; revoke/cancel there separately under authorization.

Drive/SharePoint/CRM, official case status and document repositories can be used through available host tools for explicitly scoped reads and professional handoffs. They have no built-in write adapter in v2.0. No Slack/SMS/WhatsApp transport, bidirectional sync, webhook receiver, shared-tenant authorization or government API is shipped. Add a new adapter only with a tested payload contract, a permission/disclosure policy and documented readback/reconciliation.

Technical references checked 2026-10-31: [Google events.insert](https://developers.google.com/workspace/calendar/api/v3/reference/events/insert), [Microsoft Graph event](https://learn.microsoft.com/en-us/graph/api/resources/event?view=graph-rest-1.0). Recheck current API/tool documentation when executing. Provider privacy settings reduce exposure; they do not make a shared account confidential or suppress all provider-generated messages.
