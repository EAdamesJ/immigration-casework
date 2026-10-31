# v1.1 local tools

Run Python 3.10+ using the absolute installed skill path:

```bash
python3 "$SKILL_ROOT/scripts/visitor.py" readiness --profile /private/path/visitor-profile.json
python3 "$SKILL_ROOT/scripts/visitor.py" interview --profile /private/path/visitor-profile.json --language es
python3 "$SKILL_ROOT/scripts/visitor.py" bulletin --snapshot /private/path/bulletin.json --category F2A --country "All Chargeability Areas Except Those Listed" --priority 2024-01-01 --as-of 2026-10-31 --process consular
```

Copy the blank worksheet/synthetic snapshot from assets to a private location and replace its values. Neither example is a live case or current bulletin data. Helpers use only local JSON and make no network requests. readiness emits topic names and coverage rather than the applicant's answers. interview emits a question queue; the host conducts the adaptive session and qualitative review. bulletin compares one exact category/chargeability pair in both charts. It does not infer chargeability or recognize every possible immediate-relative subclass: the agent must establish applicability first.

Exit codes: 0 for a computed result (including missing rows/waiting/incomplete preparation); 2 for invalid input. Results never authorize filing or decide eligibility. No model/API key, voice capture, background scheduler or browser automation is included.
