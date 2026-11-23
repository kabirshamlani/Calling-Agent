# 0002. LiveKit Agents as the voice framework

Status: Accepted · 2026-11-22 · replaces an earlier pick of Pipecat

## The question

Something has to carry audio between the phone line, speech to text and text to speech, and handle the caller interrupting. Which framework?

## What we compared

| Option | For | Against |
| --- | --- | --- |
| **LiveKit Agents** | Our process dials out to LiveKit, so it needs no public address, no tunnel and no webhook. One free US phone number. The same code serves phone and browser callers. Hanging up is one call: delete the room. | Every voice run goes through LiveKit Cloud. More of the audio behaviour lives in their platform than in our code. |
| **Pipecat** | The whole pipeline is visible Python. No platform account needed. | Needs a phone carrier account, a public server or tunnel, and separate keys for speech and models. More parts to stand up before the first call. |
| **Hosted platforms** (Vapi, Retell, Bland) | A working number in minutes. | The agent becomes a settings page. Scope decisions and hang-up timing happen where we cannot test them. |
| **Write it ourselves** on a raw audio stream | Full control. | Audio encoding, turn detection and interruption are solved problems. |

## Decision

LiveKit Agents, pinned to one version.

## Why

We first chose Pipecat for being readable. Then we counted what a first phone call needed with each. Pipecat needed a phone carrier account, a tunnel and a webhook before anything rang. LiveKit needed a free account and a routing rule. For an agent whose own logic is a few hundred lines, the simpler setup won.

The part that matters to us is still ours. We give the LiveKit session no language model. When the caller finishes a sentence, LiveKit hands us the text, and from there our code asks the model, runs the gate and says the result ([ADR 0004](0004-scope-decision-as-a-label.md)).

## What we give up

- Independence. If LiveKit Cloud is down, nothing answers.
- Fine control of turn-taking. We use their defaults and one setting.

## Revisit when

The agent has to run inside a customer's own network, with no outside platform in the path.
