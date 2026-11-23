# 0007. Deepgram for hearing and speaking

Status: Accepted · 2026-11-23

## The question

Which services turn the caller's audio into words, and our words into audio?

## What we compared

| Option | For | Against |
| --- | --- | --- |
| **Deepgram Flux (hearing) and Aura-2 (speaking), with our own key** | One free account does both, with $200 of credit. Flux decides for itself when the caller has finished. Aura-2 starts speaking about 0.3 seconds after it gets the words (measured). | A second account besides LiveKit. |
| The same two models through LiveKit's inference service | No extra key. | LiveKit's free allowance for speech and models is small. Ours ran out after about 1,500 model requests and a dozen test calls, and then nothing answered. |
| Cartesia Sonic for the voice | The most natural voice we looked at | Costs more per call |
| Local models (Whisper, Kokoro) | Free | Slow on a laptop, and they compete with the call for CPU |

## Decision

Deepgram Flux and Aura-2, called directly with our own key.

## Why

We started on LiveKit's built-in service because it needed no extra key. Its free allowance ran out in a day of testing and the agent went silent. The same Deepgram models with our own key cost nothing for a long while and do not stop.

Over a phone line, narrow audio hides most of the gap between a good voice and a great one. With a budget we would try Cartesia Sonic for the voice. It is a one-line change.

## What we have not measured

How well Flux hears accents, account-style numbers and names on a real phone line. Almost all our test calls used a computer voice, which is easier than a person on a mobile.

## Revisit when

Call logs show mis-heard words causing handoffs.
