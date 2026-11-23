# 0004. The model labels every reply. The code acts on the label.

Status: Accepted · 2026-11-21

## The question

On every turn something has to decide: answer, or hand off? Where does that decision live, and what stops a wrong answer from being spoken?

## What we compared

| Option | How it works | For | Against |
| --- | --- | --- | --- |
| **A. Similarity threshold** | Score the question against the articles. Low score means out of scope. | Cheap, fast | Does not separate near-scope questions. Measured: 79–80% right at best ([experiment 01](../05-experiments.md#01-can-a-similarity-score-decide-scope)). |
| **B. Classifier first** | A small model labels the question. Only in-scope ones reach the answering model. | The gate is its own testable step | A second model call on every turn, in series. Follow-ups like "and how long does that take?" need the whole conversation to classify. Two prompts that can disagree. |
| **C. One model with a handoff tool** | The model answers in text, or calls a `hand_off` tool. | One call. The standard pattern. | Nothing marks a normal answer as checked: text with no tool call is spoken as is. Tool calls and speech arrive in separate channels, and frameworks have ordering bugs there. Weaker on open models. |
| **D. One model, JSON reply** | The model returns `{action, article, text}`. | Always a typed decision | Speech has to wait for, or carefully stream out of, a JSON string. |
| **E. One model, label first** | The reply starts with `[answer:02]`, `[handoff:reason]` and so on. The code reads the label, then acts. | One call. Decision known in the first few tokens. Every turn is typed. Unlabelled text is never spoken. Works on any model. | We write a small parser. The label format is a convention the model has to follow. |

## Decision

Option E. Labels are listed in the [design doc](../03-design.md#the-label).

Two rules make it safe:

1. **No citation, no answer.** Only `[answer:NN]` with a real article number lets model text reach the caller. A missing or malformed label is treated as a handoff.
2. **Everything else is a fixed line.** Small talk, "say that again", handoff and goodbye are spoken from a list in the code ([ADR 0005](0005-fixed-lines-and-hang-up-in-code.md)). The model picks which one. It does not write them.
3. **No new numbers.** Every number in an answer must appear in the cited article, or the answer is blocked and the call handed off.

## Why

A rule written only in a prompt holds until someone finds the sentence that talks the model out of it. So each rule we care about is also enforced by code that the caller's words never reach.

The mistake we most want to avoid is answering something we should not. Options C and E both use one model call, but they fail in opposite directions. In C, the default is to speak: if the model forgets the tool, the caller hears an answer. In E, the default is to hand off: if the model forgets the label, the caller gets a human.

Against B: the classifier adds 100–500 ms to every turn for a second opinion from a model that has less context than the first.

## What we give up

- The code checks the shape of an answer: labelled, cited, no new numbers. Whether the question was truly in scope is still one model's judgement. If it is wrong, nothing else catches it during the call. The evals have to carry that weight, which is why the scope target is zero wrong answers.
- Small talk is stiffer than it could be. Five fixed replies cover it.
- A model that drifts from the label format will cause needless handoffs. Safe, but annoying. The evals count them.

## Revisit when

The evals show wrong answers that prompt changes cannot remove. The next step is a second model, from a different provider, that checks each answer against its article while the first sentence is being spoken, and cuts in only if it objects.
