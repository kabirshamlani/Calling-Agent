# 0009. Test the brain in text first, the phone second

Status: Accepted · 2026-11-21

## The question

How do we know the agent does the right thing, and keep knowing as the prompt changes?

## What we compared

| Option | For | Against |
| --- | --- | --- |
| **Call it by hand and listen** | Catches what only a real call shows | Slow. Nobody runs 76 calls after each prompt edit. Not repeatable. |
| **A test set run in text against the brain** | Seconds per run. Repeatable. Exact pass and fail counts. | Does not cover audio, timing or hang-up |
| **Simulated phone callers** (Hamming, Coval, Cekura) | Tests the whole thing, with accents and noise | Paid platforms. Slow and costly per run. More than this needs yet. |
| **Unit tests with a fake model** | Fast and free | Tests our code, not the model's judgement. A fake model always behaves. |

## Decision

Use three of them, each for what it is good at.

1. **Text test set** for decisions and answer quality. This is the main one. Details in the [design doc](../03-design.md#how-we-check-it).
2. **Unit tests** for our own code: the label parser, the loader, the counters.
3. **Real calls by hand** for audio, interruption, timing and hang-up, with a recording kept.

No simulated-caller platform for now.

## Why

Almost every way this agent can do harm is a wrong decision by the brain, and the brain works on text. Testing it in text is fast enough to run after every prompt change, which is the only way a prompt gets better instead of just different.

Three choices inside the test set matter:

- **Two error counts, kept apart.** Wrongly answered and wrongly handed off. A single accuracy number would let an agent that hands off everything look good.
- **Three runs per case.** Models vary run to run. A case passes only if it passes every time.
- **A model as judge, from a different provider, checked by hand.** Whether a spoken answer stays true to its article is too fuzzy for string matching. A judge model does it. It comes from a different provider than the answering model, so the two do not share blind spots. We hand-label 20 answers first to confirm the judge agrees with a person.

## What we give up

Automated coverage of the audio path. A change that breaks hang-up timing will not fail any automated test. The manual call checklist covers it, and it has to be re-run when the pipeline changes.

## Revisit when

There is real call volume. Then every call gets scored from its log, and a simulated-caller run before each release starts to pay for itself.
