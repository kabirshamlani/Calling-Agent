# 0001. A text pipeline, not a speech-to-speech model

Status: Accepted · 2026-11-21

## The question

There are two ways to build a voice agent.

- **Pipeline:** speech to text, then a language model working on text, then text to speech. Three parts.
- **Speech-to-speech:** one model takes audio in and gives audio out (OpenAI Realtime, Gemini Live).

## What we compared

| | Pipeline | Speech-to-speech |
| --- | --- | --- |
| Can we read the reply before it is spoken? | Yes. It is text. | No. The model's output is the audio. |
| Record of what was heard and said | Exact text at every stage | A side transcript that [OpenAI's own guide](https://developers.openai.com/cookbook/examples/realtime_eval_guide) calls an approximation |
| Testing | The brain runs in text, in seconds | Needs audio in and audio out |
| Response time | 1 to 1.5 s when well tuned. Ours measures about 2.5 s today. | About 0.5 s claimed |
| Sounds natural, copes with noise | Good | Better |
| Swap one part | Yes | No |

## Decision

Pipeline.

## Why

The design rests on reading the model's label before anything is spoken ([ADR 0004](0004-scope-decision-as-a-label.md)). That needs text between the model and the voice. A speech-to-speech model has nothing in that gap to check.

The second reason is the record. A support line for a money product has to be able to show what the caller said and what the agent said. With a pipeline, the log is the same text the model saw.

## What we give up

Speed, and some naturalness. A tuned pipeline is about half a second slower per turn. Ours is not tuned yet. Speech recognition mistakes also flow into the model. The evals include mis-heard versions of questions to watch for that.

## Revisit when

A speech-to-speech model can hold its audio until a text decision has been checked, and gives an exact record of its input.
