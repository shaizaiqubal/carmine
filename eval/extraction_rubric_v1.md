# Carmine: Assumption-Extraction Rubric and Thresholds

**Version:** v1
**Written:** 2026-11-25
**Status:** FRROZEN BEFORE ANY RUN.

**What this scores:** the assumption extractor only (PROJECT.md step 2, checkpoint 0). It does **not** score retrieval, extraction of objections, or verification. Those are scored by `rubric_v1.md`, which starts from the confirmed assumptions in `eval/startups/*.yaml`.

**Inputs:** six pitch texts in `eval/pitches/` (clean and messy for each of Khatabook, MessMaestro, Juicero).
**Reference:** the gold assumption lists in `eval/startups/*.yaml`, plus their S/I tags (below).

---

## 1. Gold tags

S = stated in the pitch, I = implied but never said.

| Startup | S items | I items |
|---|---|---|
| Khatabook | 1, 3, 4, 5 | 2 |
| MessMaestro | 1, 2 | 3, 4, 5 |
| Juicero | 1, 2, 4, 5 | 3 |

Totals: 10 S, 5 I (numbers are the position in each YAML's `assumptions` list, 1-indexed).

---

## 2. Run protocol

- Run each of the six pitches through the extractor once, with the production prompt and model (gemini-3.5-flash-lite). Save the raw output of every run.
- If sampling temperature is above 0, also run each pitch 3 times in total and report the range, not just one run. Score the first run; use the others only for the range.
- Feed the pitch text only. Do not feed the YAML or the gold list.
- Tuning: at most 2 rounds if thresholds are missed. Log every change (what, why, which round). Never change a threshold after seeing results.
- Scoring is blind to version: shuffle the six outputs and hide the filename (clean vs. messy) until all are scored.

---

## 3. Scoring each extracted assumption

For every assumption the extractor returns, assign exactly one label.

| Label | Meaning |
|---|---|
| MATCH | States the same claim as a gold item (same subject, same belief), in any wording. Judged by me. |
| EXTRA-VALID | Not in the gold list, but the pitch text states or clearly implies it, and it is a single testable claim. |
| INVENTED | Asserts something the pitch does not say or clearly imply (a fact, number, or belief added by the model). |
| VAGUE | Too generic to test (e.g. "customers will like the product"). |
| DUPLICATE | Repeats another extracted assumption from the same run. |

**Matching rules:**
- One extracted assumption matches at most one gold item, and one gold item is matched at most once.
- If an extracted assumption is narrower or broader than a gold item but plainly about the same claim, count it as MATCH.
- If an extracted assumption merges two gold items into one, match it to the closer one and count the other as missed.
- A **testable claim** is one sentence that could be supported or contradicted by evidence.

**Per gold item:** FOUND or MISSED, per run.

---

## 4. Metrics

Report per startup, per version (clean / messy), and pooled.

| Metric | Definition |
|---|---|
| Recall (S) | S gold items FOUND / S gold items |
| Recall (I) | I gold items FOUND / I gold items (reported only; no threshold) |
| Invented rate | INVENTED / all extracted |
| Precision | (MATCH + EXTRA-VALID) / all extracted |
| Count | number of assumptions returned per run |
| Clean vs. messy gap | Recall (S) clean minus Recall (S) messy, per startup |

Always show raw counts next to percentages, and state n.

---

## 5. Pass thresholds

### Hard rules (any miss = fail)
| # | Rule |
|---|---|
| H1 | Every extracted assumption is returned as `proposed`. The extractor never marks anything `confirmed` (checkpoint 0 belongs to the founder). |
| H2 | Every run returns between 3 and 10 assumptions (PROJECT.md step 2). |

### Good-enough rules (all must be met)
| # | Rule |
|---|---|
| E1 | Recall (S), pooled over the 3 clean pitches: at least 80% (8 of 10) |
| E2 | Recall (S), pooled over the 3 messy pitches: at least 70% (7 of 10) |
| E3 | Invented rate, pooled over all six runs: at most 10% of extracted assumptions |

Not thresholded, but reported: Recall (I), precision, VAGUE and DUPLICATE counts, and the clean vs. messy gap per startup.

**If all rules are met:** extraction is good enough to ship to the onboarding flow.
**If any is missed:** tune and rerun (max 2 rounds, logged). If still failing, report the numbers as they are and say what the founder checkpoint must cover.

Note: MessMaestro has only 2 S items, so one miss there moves its recall by 50 points. Read the pooled numbers and raw counts, not per-startup percentages, for that one.

---

## 6. Limitations to state in the writeup

- **Circular gold.** I wrote the gold lists from these same pitches, so Recall (S) is partly measuring agreement with myself. The invented rate and the clean vs. messy gap are less biased signals.
- **I wrote the pitches.** They are simulations of founder writing, not real founder documents. Real pitches may be messier or vaguer.
- **One scorer, small n.** Six runs, 15 gold items.
- **Tuning leakage.** If the extraction prompt is tuned on these six pitches, final numbers are optimistic. Check at least one pitch not tuned on, or a fourth startup.
- **Self-consistency.** After a few days, re-label 10 random extracted assumptions without looking at the first labels and report the agreement rate.

---

## 7. Scoring log (one row per extracted assumption)

| Pitch file | Run | Extracted assumption (copy exactly) | Label | Gold item matched (if any) | Partial? | Notes |
|---|---|---|---|---|---|---|
| | | | | | | |

**Gold item results (per pitch, per run):**

| Pitch file | Gold 1 | Gold 2 | Gold 3 | Gold 4 | Gold 5 |
|---|---|---|---|---|---|
| khatabook_clean | | | | | |
| khatabook_messy | | | | | |
| messmaestro_clean | | | | | |
| messmaestro_messy | | | | | |
| juicero_clean | | | | | |
| juicero_messy | | | | | |

**Totals:** Recall (S) clean ____/10, messy ____/10 | Recall (I) ____/5 | Invented ____/____ | Precision ____
