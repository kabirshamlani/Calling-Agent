# 0008. A LiveKit phone number

Status: Accepted · 2026-11-22

## The question

How does a real phone call reach the agent?

## What we compared

| Option | Cost to start | For | Against |
| --- | --- | --- | --- |
| **LiveKit phone number** | Free. One US local number, 50 inbound minutes a month. | No carrier account. Calls arrive in the same place the agent already listens. | US numbers only. 50 minutes is not much. |
| Twilio number into LiveKit | About $20 | More minutes, numbers in more countries | A second account, plus trunk setup |
| Twilio trial | Free | | Cannot stream call audio. Does not work. |
| Browser call only | Free | Nothing to set up | Not a phone call. Cleaner audio than a real line, so it hides problems. |

## Decision

One LiveKit number. A routing rule ([`telephony/dispatch-rule.json`](../../telephony/dispatch-rule.json)) puts each caller in a fresh room and sends our agent to it.

## What we give up

Callers outside the US pay international rates. And 50 free minutes will run out fast if many people try it.

## Revisit when

The minutes run out, or callers need a local number in another country. Then add a Twilio number in front. The agent code does not change.
