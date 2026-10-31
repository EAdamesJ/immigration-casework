# Contributing

We welcome improvements that make immigration research and preparation more traceable, usable, and honest about uncertainty.

## Keep private cases private

Use wholly synthetic examples. Never attach notices, receipts, A-Numbers, addresses, financial records, medical details, children's information, credentials, or actual chat transcripts. Text redaction alone does not guarantee anonymization. If a bug needs a document, reproduce it with invented text.

## Good first contributions

- Reproducible directory/installation compatibility reports with host version and OS.
- Better English/Spanish output templates.
- Calendar, schema, or reference-integrity edge cases.
- Source-verification improvements supported by current primary sources.
- Synthetic evaluation cases that expose an unsupported assumption.

## Workflow

1. Explain the problem and observable desired behavior in an issue or focused pull request.
2. Keep the installable skill lean; put user/community docs outside its bundle.
3. For behavior changes, add a synthetic scenario and identify what must be verified. For code, test the relevant contract/failure mode.
4. Run `python3 -m unittest discover -s tests -v` and `python3 scripts/validate_repo.py`.
5. Describe what changed, what actually ran, and known limits. Do not claim native model compatibility from a file-copy test.

Do not add hardcoded current fees, guaranteed outcomes, hidden permissions/hooks, portal scraping, automatic filing, or case-data uploads. Propose substantial changes to data access and external actions before implementing them.

Contributions are provided under the repository's MIT license. Be respectful, precise, and open to evidence. Maintainers may request revisions or decline changes outside the project's scope.
