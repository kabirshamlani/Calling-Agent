# 0006. Which language model

Status: Accepted · 2026-11-22 · changed 2026-11-23, see the end · decided by [experiment 02](../05-experiments.md#02-which-model)

## The question

One model does two jobs on every turn: pick the action and write the reply. Which model?

## What it has to be good at

In order:

1. **Following the scope rule.** No out-of-scope answers.
2. **Speed.** Nothing is spoken until the reply is back.
3. **Staying inside the articles** when it rewrites them for speech.
4. **Cost**, last. Every option costs well under a cent per call.

## What we compared

All three ran the same 76 questions with the same prompt.

| Model | Wrongly answered | Wrongly handed off | Typical reply time |
| --- | --- | --- | --- |
| **Gemini 3.1 Flash-Lite** | 0 of 144 | 0 to 4 of 84 | 0.75 to 1.3 s |
| GPT-5.4 mini | 0 of 144 | 1 of 84 | 0.93 s |
| gpt-oss-120b (open weights) | 3 of 48 | 4 of 28 | 1.16 s |

The first two rows are three runs each. The open model was dropped after one run. Only the Gemini row has a saved result file. The other two were read off the runs as they finished, before the free credit ran out.

## Decision

Gemini 3.1 Flash-Lite.

## Why

It tied for zero wrong answers and was the fastest in the comparison run. In that run its four wrong handoffs were two dropped connections and two answers our own number check blocked, correctly, for quoting a figure from a different article than the one cited. A later run of the same set had none.

The open-weight model answered out-of-scope questions, once inventing a feature ("you can edit the recipient details"), and returned empty replies three times. We wanted an open model to work, because it could run inside a customer's own network. On this task it is not there yet.

The comparison ran through LiveKit's inference service, which let us try three models on one key. The agent now calls Gemini directly with our own Google key, because that service's free allowance ran out. Claude Haiku was on our list. LiveKit does not offer it and we had no separate key, so it was not tested. It may well do better.

## Changed a day later: Gemini 3.5 Flash-Lite first, 3.1 as backup

On 30 fresh questions 3.1 Flash-Lite answered two it should not have, on every run. We tightened three rules and ran both models three times on a paid key:

| Model | Main set wrongly answered | Held-out wrongly answered | Median reply |
| --- | --- | --- | --- |
| **Gemini 3.5 Flash-Lite** | 0 of 150 | 0 of 60 | 0.93 s |
| Gemini 3.1 Flash-Lite | 0 of 150 | 2 of 60 | 0.74 s |

Scope is first on the list above and speed is second, so 3.5 Flash-Lite takes the calls. It costs about 0.2 seconds a turn. If it errors or takes over five seconds, 3.1 Flash-Lite gets the same request.

A free Google key still works, with a cap of 500 requests a day per model, and on it 3.5 Flash-Lite is slow, about three seconds a reply.

## The weak spot

The prompt was tuned on those 76 questions. On 30 fresh questions the same model wrongly answered 2, every run. Details and the two cases are in [experiment 02](../05-experiments.md#02-which-model). Zero on the tuned set does not mean zero in the world.

## Revisit when

A model is released or retired, or the test set grows. Re-running the comparison is one command.
