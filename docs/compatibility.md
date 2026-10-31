# Compatibility and verification scope

Documentation review date: 2026-10-31. Recheck upstream behavior when updating the package.

| Environment | Format and location | Verification completed here | Not claimed |
| --- | --- | --- | --- |
| Codex local skills | SKILL.md in user/project `.agents/skills/`; optional agents/openai.yaml | Official documentation read; directory-copy and package checks | A live Codex model session on each OS |
| Claude Code | SKILL.md in user/project `.claude/skills/`; optional skill-only plugin | Official documentation read; directory-copy and package checks | Installation into a Claude chat account/Cowork through a filesystem copy |
| DeepSeek Harness | Directory bundle under project `.dsh/skills`, shared `.agents/skills`, user DSH or configured roots | First-party filesystem-provider documentation read; local-copy path checks | An enabled provider in every distribution or a live DeepSeek model session |

The shared skill uses only `name` and `description` frontmatter; no harness-specific shell injection or preapproved-tool rules are required. Core instructions and references are Markdown. Optional scripts require Python 3.10+. The host supplies browsing, OCR/document readers, authentication, and any permitted external actions; installing a skill grants none of that access.

## Sources

- [OpenAI local skill discovery](https://learn.chatgpt.com/docs/build-skills).
- [OpenAI plugin packaging](https://developers.openai.com/plugins/build/plugins).
- [Claude Code skills](https://code.claude.com/docs/en/skills).
- [Claude plugin manifest reference](https://code.claude.com/docs/en/plugins-reference).
- [DeepSeek filesystem skill provider](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/skill/skill-filesystem/README.md).
- [DeepSeek skill subsystem](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/skills.md).

DeepSeek's documented provider scans bundles one level deep. Copy the skill directory directly into the selected root; do not copy the whole repository as one nested skill. User `DSH_HOME` is honored by the installer. The provider and skill registry must be enabled; this package does not change Cordis configuration. The provider also documents a user shared-agents root, but the dedicated DSH destination avoids relying on that configuration.

Claude Code's local personal folder, Claude-account skills, Cowork, and cloud sessions are different installation surfaces. Codex account-managed skills also differ from a filesystem installation. Follow the destination product's current account/import process for those surfaces. The repository does not promise automatic synchronization across products or devices.

## Installation behavior

The primary installer operates on reviewed files from a local clone. It performs no network calls or shell downloads. Dry run reports destinations without creating directories. Identical installations are unchanged; conflicting copies require explicit `--replace` and are retained in a backup outside the skill scanner. A failed per-target replacement attempts to restore its previous copy. Multi-target installs preflight paths but are not one atomic transaction.

Symbolic links in source/destination paths are refused to keep copying predictable. No uninstall command removes files: disable/remove the dedicated installed directory through the host's ordinary skill management. Backups remain for manual review/recovery. Installing to system/admin directories is outside this installer's scope.

## Test interpretation

Unit tests validate date edge cases, input shape, reference integrity, selected consular-stage/chronology warnings, privacy-sensitive output behavior, redaction limits, path selection, copying, backups, and failure recovery. Package checks validate metadata, local documentation links, version alignment, and selected secret/identifier patterns. The CI matrix defines additional platforms; a workflow file alone is not evidence that every hosted job has run.

Behavioral evaluation uses synthetic tasks and a stated rubric. It cannot establish universal legal accuracy or equivalent behavior across models. Test reports must name the actual host/model when known and mark it unknown when not available. No current fees, policy outcomes, processing-time promises, or private case details are embedded in fixtures.
