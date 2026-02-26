# AGENTS.md — backend/evaluation

> 7-dimension evaluation framework for literature review quality assessment.

## Overview

Automated + human evaluation of generated reviews. Called via `POST /api/research/evaluate` and `runner.run_evaluation()`.

## Dimensions

| Dimension | Module | Metric |
|-----------|--------|--------|
| Citation precision | `citation_metrics.py` | % of `[N]` where 1 ≤ N ≤ approved_count |
| Citation recall | `citation_metrics.py` | % of approved papers actually cited |
| Claim support rate | via `claim_verifier.py` | Entailment ratio from verification summary |
| Section completeness | `section_completeness.py` | Required sections present (aliases in `constants.py`) |
| Academic style | `academic_style.py` | Hedging ratio, passive voice, citation density |
| Cost efficiency | `cost_tracker.py` | Token counts, USD cost, per-node timing |
| Human ratings | `human_ratings.py` | 1-5 scale stored in `data/ratings.json` |

## Key Files

| File | Lines | Role |
|------|-------|------|
| `schemas.py` | 201 | All evaluation Pydantic models with `@computed_field` properties |
| `cost_tracker.py` | 163 | Module-level lists for usage/timing/search records. Pricing table for OpenAI + DeepSeek |
| `runner.py` | 77 | Orchestrates all dimensions, merges log-parsed + runtime-tracked cost data |
| `citation_metrics.py` | ~60 | Regex-based citation extraction (`{cite:N}` and `[N]` formats) |
| `academic_style.py` | ~70 | Sentence splitting, hedging/passive counting, bilingual (en/zh) |
| `section_completeness.py` | ~60 | Heading normalization + alias matching from `constants.py` |
| `human_ratings.py` | ~60 | JSON file storage in `data/ratings.json` |

## Conventions

- All evaluation functions are synchronous (no async) — they operate on in-memory data
- `cost_tracker.py` uses module-level mutable lists (`_usage_records`, `_timing_records`) — not thread-safe, reset between runs
- Bilingual support: most functions accept `language: str` param (`"en"` or `"zh"`)
- Required sections and hedging patterns defined in `backend/constants.py`, not here
- Citation patterns: `CITATION_PATTERN` for `{cite:N}`, `NORMALIZED_CITATION_PATTERN` for `[N]`

## Adding a New Dimension

1. Create `backend/evaluation/new_dimension.py` with a pure function returning a Pydantic model
2. Add the result model to `schemas.py`
3. Add the field to `EvaluationResult` in `schemas.py`
4. Call the function in `runner.py:run_evaluation()`
5. Add tests in `tests/test_evaluation.py`
