# Carmine: Validity Rubric and Pass Thresholds

**Version:** v1
**Written:** 2026-11-25
**Status:** FROZEN BEFORE ANY RUN

**Test startups:** Khatabook, MessMaestro, Juicero
Gold assumption lists live in the three YAML files in this folder.

---

## 1. What gets scored

**Unit:** one card (objection + quote + source URL + assumption). Score the cards the founder would actually see (top N after verification and ranking), not raw extractions.

**How to score:**
- Shuffle the cards.
- Hide module, rank, severity, confidence, and model support scores. (I wrote the code, so I blind myself to its opinion.)
- Score the gates below in order. Stop at the first fail and record which gate failed.

---

## 2. The four gates

### Gate 1: Source is real
- The URL loads, or is in the cache with fetched text saved.
- The quote appears verbatim in that text (string match, whitespace and case ignored only).
- The source date is within the recency window (default 3 years). Older sources pass only if the objection is explicitly about history (e.g. a past failure pattern).
- **Juicero capped run only:** the source must predate the cutoff date (2016-12-31).
- A Gate 1 failure on a surfaced card is a pipeline bug, not a quality problem. Log it separately.

### Gate 2: Quote supports the objection
Pick one:
- **FULL:** the quote directly states or clearly implies the objection.
- **PARTIAL:** same topic, loosely related, objection overreaches the quote.
- **NONE:** the quote does not support the claim.

Only FULL passes. Keep the PARTIAL count anyway: it shows how generous the support check is.

### Gate 3: Relevant to the assumption
- It bears on the named assumption. A reasonable reader can see why this evidence threatens that specific belief.
- For general cards (assumption = null): it must bear on **this** startup's model, not startups in general.

### Gate 4: Specific
- Names a concrete thing: a competitor, number, behavior, rule, or event.
- **Swap test:** put a different startup in. If the card still reads fine, it fails.
- "Customers might not pay" fails.
- "Users in the thread say they stay on the free tier because X" passes.

**Result per card:** VALID (passes all four) or INVALID (record the first failed gate).

---

## 3. "Low evidence found" cards

Scored separately, not part of the valid rate.
- **Pass:** the card honestly says evidence is thin and carries no invented quote or source.
- **Fail:** it carries any fabricated or unsupported claim.

Tracked as the honesty rate. Expect many of these for MessMaestro.

---

## 4. Not part of validity

- Tester labels (new / useful / obvious / wrong).
- My own opinion of severity.

A card can be valid but obvious. Track that separately.

---

## 5. Pass thresholds

### Hard rules (zero tolerance, any miss = fail)
| # | Rule |
|---|---|
| H1 | Gate 1 passes on 100% of surfaced cards |
| H2 | "Low evidence found" honesty is 100% (no invented evidence) |

### Good-enough rules (all must be met)
| # | Rule |
|---|---|
| S1 | Gate 2 (FULL support) passes on at least 85% of cards |
| S2 | Overall valid rate is at least 60%, pooled across Khatabook and Juicero |
| S3 | No single startup (Khatabook, Juicero) below 50% valid |

MessMaestro is judged on honesty only (H2), not on valid rate. Reason: it is meant to be thin, and a valid-rate target would push me to tune the module into inventing objections.

With about 8 cards per startup, one card moves a rate by about 12 points. Report raw counts next to every percentage, and state n.

### What happens next
- **All rules met:** move on to the queue.
- **Any missed:**
  - Fix and rerun, at most 2 tuning rounds.
  - Log every change made between rounds (what, why, which round).
  - If still failing after 2 rounds, report the numbers as they are and decide whether to narrow scope or accept a lower bar, in writing, with the reason.
  - Never lower a threshold after seeing results.

---

## 6. Guardrails

**Overfitting.** If prompts are tuned using these three startups, the final numbers are optimistic. For the final check, use something not tuned on: the messy version of a startup I did not tune on, or a fourth startup. State this as a limitation either way.

**Self-consistency (I am the only scorer).** Re-score 10 random cards after a few days without looking at my first scores. Report the agreement rate. If agreement is low, tighten the wording of whichever gate I flipped on.

**Scorer limits.**
- One scorer, small n, student-built test set: state all three in the writeup.
- Juicero's outcome is known to me: state that the Juicero manual list is not blind.

**Optional, later.** Run the same assumptions through a plain chatbot prompt and score with the same rubric, for the Carmine-vs-chatbot comparison.

---

## 7. Manual baseline log (one block per startup)

**Startup:** ____________________
**Date:** ____________________
**Time box:** 30-45 minutes. Stop when the timer ends.

**Minutes spent**
- Searching: ______
- Reading: ______
- Writing up: ______
- Total: ______

**Aware of the real outcome beforehand?** (yes / no): ______

**Objections I would put in a queue** (score each with the rubric above):

| # | Objection (1-2 sentences) | Source URL | Exact quote | Assumption id | G1 | G2 | G3 | G4 | Valid? |
|---|---|---|---|---|---|---|---|---|---|
| 1 | | | | | | | | | |
| 2 | | | | | | | | | |
| 3 | | | | | | | | | |
| 4 | | | | | | | | | |
| 5 | | | | | | | | | |

- Valid risks found: ______
- Minutes per valid risk (total minutes / valid risks): ______

**Notes** (what was hard, what was missing): ____________________