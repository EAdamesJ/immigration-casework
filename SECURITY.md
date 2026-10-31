# Security and privacy

Supported line: current 1.x release. This is a small independent project; no response-time commitment is implied.

## Reporting a vulnerability

Use GitHub private vulnerability reporting if it is enabled for this repository. Otherwise open a minimal issue asking for a private contact channel, without exploit details or sensitive data. Never include an actual immigration case, patient record, credential, or government identifier in a public report.

## Design boundaries

The bundled helper and installer use local files and no network. They include no live status integration, model API calls, hooks, credential storage, or submission automation. They do not control the data handling, permissions, or telemetry of an AI host or its other tools. The skill explicitly treats retrieved documents as evidence rather than instructions.

Private case scaffolds are created outside Git workspaces and receive a protective .gitignore; POSIX permissions are restricted when created. These measures are not encryption, authentication, sandboxing, or a guarantee against deliberate force-add, compromised machines, symlink races, or third-party synchronization. Windows ACLs require appropriate local configuration.

Redaction is best effort and covers selected text patterns only. Source-host classification is an allowlist check, not page verification. Structural auditing cannot authenticate documents or decide legal sufficiency. Never use those outputs as a substitute for the stated human/source review.

## Out of scope

Legal disagreements, agency decisions, individual case delays, host-model behavior outside this workflow, and security issues in third-party agents belong to the appropriate provider or qualified professional. Reproducible package defects, unsafe file handling, accidental data transmission, credential exposure, and prompt-injection paths introduced by this package are in scope.
