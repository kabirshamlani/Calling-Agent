# 0003. The whole FAQ goes in the prompt. No search.

Status: Accepted · 2026-11-21

## The question

The model needs the six articles to answer. Do we give it all of them on every turn, or search for the relevant passage first (retrieval, often called RAG)?

## The facts

- Six articles. 2,300 words. About 3,500 tokens.
- Current models take prompts of 200,000 tokens or more.
- The articles overlap. Four of the six talk about delays at the recipient's bank. Three explain the receipt.

## What we compared

| | Whole FAQ in the prompt | Search first |
| --- | --- | --- |
| Extra step per turn | None | One search before the model call |
| Can miss the right passage | No. It is always there. | Yes. Overlapping articles make the wrong sibling likely. |
| Follow-up questions | Work. The model has everything. | Need the search query rewritten from the conversation |
| Cost per turn | 3,500 input tokens, mostly cached | A few hundred tokens |
| Parts to build and test | Zero | Chunking, an index, a search step, a threshold |

## Decision

Put all six articles in the system prompt, in a fixed order, so the provider caches them.

## Why

Search solves the problem of knowledge that does not fit. Ours fits about fifty times over. Adding search would add a way to fail and remove nothing.

There is a second, less obvious reason. Search is often used as the scope check: "if nothing relevant comes back, the question is out of scope". We tested that. It does not work here, because out-of-scope questions about transfers look very similar to in-scope ones. "How do I send money with Wise?" scored higher than most valid questions. Full numbers in [experiment 01](../05-experiments.md#01-can-a-similarity-score-decide-scope).

## What we give up

A few thousand input tokens per turn. With caching, that is a fraction of a cent per call.

## Revisit when

Any of these becomes true:

- The knowledge passes roughly 50,000 tokens. Past that, time to first token and cost start to show.
- The knowledge changes daily, or differs per customer.
- Answers need account data, which is a lookup, not a document.

When that happens, add search for finding passages, keep the scope decision with the model, and re-run the scope evals before and after.
