# Pull Request

## What changed

<!-- One paragraph. Link the decision (D1–D5) or PDT section this implements. -->

## Evidence

<!-- Links to source text / URLs / batch ids that support the change. -->

## Checks

- [ ] `scripts/check-no-secrets.sh` passes
- [ ] No CX internal data, no real review full text in bulk, no real questionnaire raw answers
- [ ] No API keys, tokens, or `.env` values committed
- [ ] All example data is labelled synthetic

## Jev changes (if any)

- [ ] Model version change: gold-standard re-run record attached (required — see PDT v1.2 §6.1, J-9)
- [ ] Choice configuration: every Choice has a None option and the Noul gate "是否属于现有意图清单" is live (J-10)

## Intent registry changes (if any)

- [ ] Registry version bumped and change log entry added (merge/split/definition change with date, reason, before/after)
