# Maintainer guide

## Make a focused change

Keep the installable bundle in `skills/us-immigration-casework/` lean. Put detailed task-specific guidance in references, reusable output skeletons in assets, and deterministic offline operations in scripts. Keep community/install documentation at the repository root or under docs, outside the skill bundle.

Do not add hooks, network scraping, credentials, external transmission, model APIs, or automatic filing as an incidental change. Changes in data access or external actions need explicit design, tests, and documentation. Avoid static current-law claims: route volatile facts to live primary-source verification.

For each behavioral change add a synthetic scenario and explain the failure it prevents. For code changes add tests of an observable contract or realistic failure; avoid tests that merely repeat source text. No real case, trace, patient record, or user prompt belongs in a fixture.

## Verify

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate_repo.py
python3 scripts/install.py --target all --dry-run
```

Use isolated destinations for installation smoke tests, not another person's real agent configuration. Review rendered README/cover and bilingual instructions. Recheck upstream compatibility sources after changes to manifests, directories, or invocation syntax.

## Behavioral review

Follow [the evaluation guide](../evals/README.md). Present the evaluator only the task and raw synthetic artifacts. Do not leak the expected answer or prior diagnosis. Keep outputs private until reviewed for data leakage. Distinguish human/agent review from automated unit tests and report what actually ran.

## Release

Update VERSION, both plugin manifests, and the CLI version together. Add a factual changelog entry. Run package/tests and review the staged diff for credentials and case data. Check that example URLs and the repository name match the publication destination. Tag a release only after the target branch and hosted checks are verified; never publish a fabricated CI success badge or behavioral score.

Publish notes naming capabilities, supported formats, verification performed, and material limits. Do not advertise government affiliation, professional licensing, guaranteed approval, guaranteed deadlines, fabricated testimonials, star counts, or native-runtime testing that did not happen.
