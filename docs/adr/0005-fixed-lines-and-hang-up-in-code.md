# 0005. Fixed lines and the hang-up belong to code

Status: Accepted · 2026-11-21

## The question

Who says the handoff line, and who ends the call?

## What we compared

| Option | For | Against |
| --- | --- | --- |
| **The model writes the handoff line and calls an end-call tool** | Flexible wording | The wording changes call to call. Models often send the tool call with no text, so nothing is said. Or the hang-up fires while the line is still playing. |
| **Hang up when the agent says a trigger phrase** | Simple | A model that says "goodbye" in passing drops the call. |
| **The code speaks a fixed line and hangs up when the audio has finished** | Same words every time. The ordering is ours to control and test. | The line cannot adapt to the caller. |

## Decision

The code owns it. When the label is `handoff` or `end`:

1. Drop whatever text the model wrote.
2. Stop listening to the caller.
3. Speak the fixed line.
4. Wait until the audio has been played out, plus a short pad for the phone network.
5. End the call through the carrier's API.
6. Log the action and the reason.

The greeting, the "didn't catch that" line and the small-talk replies are fixed too. That leaves cited answers as the only words the model composes.

## Why

Cut-off goodbyes and calls left hanging are a known class of bug across voice frameworks. The issue trackers have reports of it, for example in [Pipecat](https://github.com/pipecat-ai/pipecat/issues/1461) and [LiveKit Agents](https://github.com/livekit/agents/issues/8010). They all come from the same cause: the model, the audio queue and the phone line each think they decide when the call ends. Giving that to one piece of code removes the race.

A fixed line also means the one sentence every handed-off caller hears has been written and approved by a person.

Step 2 matters. Without it, a caller who talks over the handoff line starts a new turn, and the agent can end up answering after it decided to hand off.

## What we give up

A handoff line that speaks to the caller's situation ("I can't help with refunds, but…"). A fixed line can sound abrupt. We accept that for now. A later version could pick from a few approved lines by handoff reason.

## Revisit when

There is a real transfer to a human queue. Then step 5 becomes "transfer" and the line changes to match.
