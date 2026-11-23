# Experiments

What we measured, and what it changed. Each experiment has a script anyone can re-run.

| # | Question | Status | Feeds |
| --- | --- | --- | --- |
| 01 | Can a similarity score decide scope? | Done | [ADR 0003](adr/0003-whole-faq-in-the-prompt.md), [ADR 0004](adr/0004-scope-decision-as-a-label.md) |
| 02 | Which model? | Done | [ADR 0006](adr/0006-language-model.md) |
| 03 | How fast is a turn? | First measurement done | [architecture](04-architecture.md#where-the-time-goes) |

## 01. Can a similarity score decide scope?

**Why we asked.** A common design is to search the knowledge base with the caller's question and treat a low match score as "out of scope". It is cheap and needs no model call. If it worked, it would be the simplest gate there is.

**What we did.** Took the 65 test cases that are either `answer` or `handoff`: 28 in scope and 37 out. Split the six articles into 29 passages. Scored each question against every passage and kept the best score. Tried two scorers: a dense embedding model (bge-small-en-v1.5) and keyword matching (BM25). Then looked for the threshold that best separates the two groups.

**What we found.**

| Scorer | Best accuracy at any threshold | Wrongly answered | Wrongly handed off | Valid questions lost if we allow zero wrong answers |
| --- | --- | --- | --- | --- |
| Embeddings | 79% | 2 | 12 | 22 of 28 |
| BM25 | 80% | 3 | 10 | 20 of 28 |

No threshold works. The scores of the two groups overlap almost completely.

The questions that fool it are the ones that matter most (embedding scores):

| Score | Question | Should be |
| --- | --- | --- |
| 0.829 | What's a proof of payment and what are your fees? | hand off |
| 0.798 | How do I send money with Wise? | hand off |
| 0.780 | My transfer number is 1 2 3 4 5 6 7 8, can you tell me its status? | hand off |
| 0.671 | I think I typed one letter wrong in the name. Will that slow it down? | answer |
| 0.648 | It's been stuck on processing for three days now. | answer |
| 0.608 | What can I do to make it go faster? | answer |

**What it means.** A similarity score measures whether a question is about the same subject as the articles. Scope is a different thing: whether the articles contain the answer. "How do I cancel my transfer?" is on the subject and not in the articles. Real callers also describe a situation ("it's been stuck for three days") in words the articles never use.

So the scope decision needs something that reads the question and the articles and reasons about them. That is the language model.

**Limits.** One small embedding model, one way of splitting passages, 65 questions that we wrote ourselves. A larger model or a reranker would do better. We did not chase that, because the gap to "zero wrong answers" is too wide to close by tuning.

**Run it.**

```bash
uv run --with fastembed --with rank-bm25 --with pyyaml --with numpy experiments/01-scope-by-similarity/run.py
```

Output: [`experiments/01-scope-by-similarity/results.txt`](../experiments/01-scope-by-similarity/results.txt)

## 02. Which model?

**Question.** Which model follows the scope rule every time, and how fast is it?

**What we did.** Ran the 76 test questions through three models, using LiveKit's inference service to reach all three on one key, each reply going through the same gate a live call uses. Same prompt for all.

**Round one: the first draft of the prompt.** One run each.

| Model | Passed | Wrongly answered | Wrongly handed off |
| --- | --- | --- | --- |
| gpt-oss-120b (open weights) | 57 of 76 | 4 | 2 |
| Gemini 3.1 Flash-Lite | 69 of 76 | 4 | 0 |
| GPT-5.4 mini | 70 of 76 | 1 | 1 |

Every model answered questions it should not have. They were all the same kind: the caller wanted something done (a refund, a fix to recipient details), and one article mentions that thing in a sentence.

**What we changed.** One idea, added to the prompt: *the articles explain things, they do not do things.* A caller who wants to understand gets an answer. A caller who wants something done or changed gets a human, even if an article mentions it.

**Round two: the tuned prompt.** Three runs each for the two best.

| Model | Wrongly answered | Wrongly handed off | Typical reply time |
| --- | --- | --- | --- |
| **Gemini 3.1 Flash-Lite** | 0 of 144 | 0 of 84 | 1.3 s |
| GPT-5.4 mini | 0 of 144 | 1 of 84 | 0.93 s |
| gpt-oss-120b, one run | 3 of 48 | 4 of 28 | 1.16 s |

**Round three: questions the prompt has never seen.** Thirty new questions, written after tuning, three runs.

| Model | Wrongly answered | Wrongly handed off |
| --- | --- | --- |
| Gemini 3.1 Flash-Lite | 6 of 60 (two questions, every run) | 0 of 30 |

**What it means.**

- Zero on the tuned set was partly the prompt learning the test. Fresh questions found two holes straight away. The held-out number is the one to believe.
- Both holes are the same shape as round one: an article touches the subject, so the model answers. The prompt rule helps and does not close it.
- The number check earned its place. In an earlier run it blocked two answers that quoted a working-day figure while citing an article that never gives one.
- The open-weight model is not good enough here. It invented a feature ("you can edit the recipient details") and returned empty replies.

**Limits.** Result files exist for the Gemini rows only. The GPT-5.4 mini and gpt-oss numbers were read off the runs as they finished, and the free credit ran out before those runs could be repeated and saved. Treat them as indicative. We wrote every question ourselves. Claude was not tested, because it is not in LiveKit's catalogue and we had no separate key. Reply times are from one laptop in India.

**Run it.** `make eval` and `make holdout`. Results land in [`evals/results/`](../evals/results/).

## 03. How fast is a turn?

**Question.** From the caller finishing a sentence to the agent starting one, how long is it?

**What we did.** One call with 13 different questions, using [`scripts/test_call.py`](../scripts/test_call.py). It joins the call the way the website does, speaks with a computer voice at real speed, and times the gap by listening for the agent's audio. The agent logs its own stages.

**What we found.**

| | Average | Median | Fastest | Slowest |
| --- | --- | --- | --- | --- |
| Caller stops to agent starts | 3.4 s | 3.2 s | 2.7 s | 5.1 s |
| Deciding the caller has finished | 0.8 s | 0.6 s | 0.6 s | 2.5 s |
| Model reply, through the gate | 1.3 s | 1.3 s | 1.1 s | 1.7 s |

All 12 covered questions were answered from the right article and the 13th, a cancellation, was handed off.

We also tried three things that did not help or would not help:

- **Speaking the first sentence early.** The model delivers its whole reply at once, so there is no first sentence to start on.
- **Turning off the model's thinking step.** 0.85 s against 0.99 s over four requests: inside the noise.
- **A faster open model.** It failed the scope tests in experiment 02.

**Interruptions.** Talking over an answer stopped the agent 0.5 and 1.0 seconds after the caller began, in two scripted runs. Then a person tried it in a browser with laptop speakers, and the agent did not stop at all. LiveKit's detector, which tries to tell a real interruption from background sound, had judged it not to be one. We switched to a plain rule: any voice for 0.3 seconds stops the agent. A scripted run after the change: quiet in 0.8 seconds.

**A second round, after the call still felt slow.**

- **Turns that skip the model.** "Say that again", "agent", "hello" and "that's all" are now matched by rule. Over eight such turns the agent started 1.5 to 2.1 seconds after the caller stopped, 1.8 typical. So 1.8 seconds is what hearing, speaking and distance cost before any model is asked.
- **A more eager end-of-turn setting.** No measurable change over five turns. Left at the default.
- **Asking the model twice and using the first reply.** It hid the slow replies, but it doubled the requests, the free daily allowance of 500 ran out, and a test call ended with a handoff. Removed.
- **A backup model.** When the first model errors or takes over five seconds, a second one gets the same request.

**Closing the two holes.** The two held-out questions were *"It was returned to you guys, when do I get my money back?"* and *"Just tell me yes or no, has my transfer gone through?"*. Three rules in the prompt were tightened: anything about a refund is out of scope, a question only the caller's account could answer is a lookup, and a jumble of words is unclear even if one word sounds like a topic. Both questions then moved to the main set and two new ones took their place in the held-out set, so that set is still made of questions the prompt has never been tuned on.

**A third round, on a paid key.**

| Model, three runs | Main set wrongly answered | Held-out wrongly answered | Median reply |
| --- | --- | --- | --- |
| **Gemini 3.5 Flash-Lite** | 0 of 150 | 0 of 60 | 0.93 s |
| Gemini 3.1 Flash-Lite | 0 of 150 | 2 of 60 | 0.74 s |

Scope comes before speed, so 3.5 Flash-Lite became the first choice and 3.1 the backup. On the free key 3.5 Flash-Lite had taken about three seconds a reply. On the paid key, with its thinking step set to minimal, it takes under one.

**Starting the model early.** The agent now asks the model as soon as the transcript ends in a full stop or question mark, without waiting for the end-of-turn check. If the final words differ, the early reply is thrown away. The same ten-question call went from an average of 2.8 seconds (2.3 to 3.3) to 2.5 (2.0 to 2.9).

Before that, we put timestamps on both ends of a call. A turn of 2.7 seconds split into: 0.7 hearing, 0.95 model, 0.3 voice, 0.7 for the agent's audio to reach the caller. Pointing speech at Deepgram's EU region, which is nearer to India than the US one, brought six turns to an average of 2.8 seconds from 3.2.

**What it means.** About three seconds is too slow for a natural call. Most of what is left is distance: the laptop is in India and every stage calls a service somewhere else. Hosting near those services is the next thing to try.

**Limits.** One laptop, one call, a computer voice. The phone path was not timed end to end: on the two real phone calls so far the model took 1.0 and 1.5 seconds, and the phone network adds its own delay on top.
