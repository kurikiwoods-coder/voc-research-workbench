# Sample Questionnaire — SYNTHETIC EXAMPLE

> **All questions, options and expected answers in this file are synthetic examples** generated from the synthetic registry in `sample-intent-registry.json`. They are not real user data and must not be reported as findings. Use this file only to test the question-generation mapping (PDT v1.2 §10.1).

- **Source intent:** INT-001 "Weigh fixed foods, see nutrition on the scale" (synthetic, unvalidated)
- **Target:** kitchen-scale users in the US market (synthetic scenario)
- **Estimated time:** 3–5 minutes (estimate, not measured)
- **Anonymity:** anonymous, no email collected (same discipline as the real forms)

## Q1 — New intent candidate (scenario multiple choice)

In the last month, what did you mainly use your kitchen scale for? (Pick up to 3)

- [ ] Weighing the same breakfast / fixed meals and seeing nutrition on the scale
- [ ] Tracking protein per portion
- [ ] Baking / cooking ratios
- [ ] Daily health logging
- [ ] Replacing a basic scale
- [ ] Other (please write in)

_Evidence: options summarised from synthetic quotes in `sample-unified-table.csv` (SYN-001, SYN-003, SYN-010)._

## Q2 — Priority between intents (forced choice)

Which matters more to you?

- ( ) Seeing nutrition directly on the scale
- ( ) More accurate weighing

## Q3 — High severity issue (experience + bother scale)

Have you ever had the app fail to sync while logging?

- ( ) Yes
- ( ) No

If yes, how bothersome was it? 0 = not at all, 4 = very bothersome.

- ( ) 0 ( ) 1 ( ) 2 ( ) 3 ( ) 4

## Q4 — Switching / abandonment signal

Under what circumstances would you replace your current scale? (Pick all that apply)

- [ ] Presets keep disappearing
- [ ] Sync keeps failing
- [ ] Food database is too thin for what I eat
- [ ] I would not replace it

## Q5 — Open question (next discovery round)

What else about weighing frustrates you? (optional, short answer)

## Q6 — Demographics (one question, optional, last)

Which age range are you in? (optional)

- ( ) Under 25 ( ) 25–34 ( ) 35–44 ( ) 45–54 ( ) 55+ ( ) Prefer not to say

---

**Publication gates (PDT v1.2 §10.3):** simulated pretest → 2–3 person real pilot → share only the fill-in link → clear pilot answers before mass send. Expected distributions for this sample are **estimates**, not real results.
