# Behavioral evaluation

Deterministic unit tests cannot establish how an agent applies a workflow to a legal-adjacent task. Evaluate separately with synthetic inputs and a stated rubric. No real case, patient, account, or agency interaction is needed.

## Run a behavioral review

1. Give a fresh evaluator the installed skill and one task/artifact from `scenarios.jsonl`. Do not provide the rubric outcome, a diagnosis, or a preferred answer in the task prompt.
2. Use an environment without live external mutations. For offline scenarios, preserve the no-network constraint.
3. Collect the actual response/tool trace and evaluate it afterward using `rubric.md`.
4. Record date, skill version, host/model if known, tools available, scenario IDs, pass/fail dimensions, specific evidence, and limits.
5. Tighten the skill when a transferable failure appears; rerun affected and previously successful scenarios in fresh contexts.

Do not advertise a universal score or cross-model certification from a few tasks. Static checks, copy/install tests, behavioral reviews, native runtime tests, and actual legal review are different evidence.

## Suite

The scenarios cover receipt-versus-notice dates, contradictory stages, technical errors, unsupported forecasts, humanitarian drafting, missing notices/deadlines, unauthorized sharing, source lookalikes, account boundaries, and parallel-proceeding ambiguity. The synthetic intake files contain fictional excerpts with no official seals or personal records.

See [validation record](validation-record.md) for the work actually performed for this release.
