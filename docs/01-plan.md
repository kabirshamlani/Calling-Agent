# Plan

## The problem

Someone sends money abroad. It does not show up when they expected. They call support and ask one thing: where is my money?

Most of these calls get the same handful of answers. The answers are already written down in six help-centre articles. A person still picks up the phone, reads them out, and the caller waits in a queue first.

A phone agent can take these calls. The hard part is the edge of what it knows. A support line for a money product cannot guess. If the agent makes up a delivery date, or tells someone how to cancel a transfer when it has never read the cancellation policy, a real person acts on that with real money.

So the agent has two jobs, and the second matters more than the first:

1. Answer questions the six articles cover, using only what the articles say.
2. Notice every question they do not cover, say so, and pass the caller to a human.

## What we are building

A phone number you can call. An agent picks up, says it is an automated assistant, and asks how it can help.

- Ask about a late or missing transfer, and it answers in a few short sentences, taken from the articles.
- Ask about anything else, and it says it will pass you to a human agent, then ends the call. There is no human queue behind it yet. Ending the call stands in for the transfer.

The six articles are the ["Where is my money?" section](https://wise.com/help/topics/5bVKT0uQdBrDp6T62keyfz/sending-money) of the Wise help centre. A snapshot lives in [`data/faq/`](../data/faq/).

## What we are not building

- **Account lookups.** The agent cannot see a caller's transfer. It explains how to check, and never pretends to have checked.
- **A real transfer to a human.** The handoff is a spoken line and a hang-up.
- **Other languages.** English only. Other languages get the handoff.
- **Outbound calls, SMS, a dashboard, user accounts.**
- **Scale work.** One call at a time is fine. The architecture doc says what would change at volume.

## How we will know it works

We measure these on a fixed set of test questions ([`evals/cases.yaml`](../evals/cases.yaml)) and on real calls.

| What | Target | Why this number |
| --- | --- | --- |
| Out-of-scope questions answered | 0 | This is the expensive mistake. One is too many. |
| In-scope questions answered | 95% or more | A handoff on a valid question is safe but wastes the caller's time. |
| Answers that say something the articles do not | 0 | The agent repeats policy. It does not write policy. |
| Time from caller finishing to agent starting | about 1 second typical, under 2 seconds at worst | Longer than that and people say "hello?" |
| Handoff line cut off by the hang-up | never | The last thing a caller hears should be a full sentence. |
| Steps to run it | one command, one phone number | If it is hard to run, nobody will run it. |

The first two targets pull against each other. An agent that hands off everything scores a perfect zero on the first row. When they conflict, the first row wins.

## Order of work

Each step ends with something that runs.

1. **Knowledge.** Snapshot the six articles. Done: [`scripts/fetch_faq.py`](../scripts/fetch_faq.py).
2. **Test questions.** Write the questions and the expected outcome for each before writing the agent. Done: 78 cases, plus 30 held-out ones written later.
3. **The brain, in text.** Question in, decision out. No audio. Done: the gate, the prompt, and the eval runner.
4. **Voice.** Done: the agent answers a call, speaks, and hangs up. Tested with a scripted caller.
5. **Phone.** Done: a number is rented and routed, and has taken two real calls.
6. **Measure.** Done: both error counts on two question sets, whole calls, and reply delay. Results are in the README.

Step 3 comes before any audio on purpose. Every rule about what the agent may say lives in the brain, and text is the fastest place to test it.

## Documents

| Doc | Answers |
| --- | --- |
| [Spec](02-spec.md) | What exactly does the agent do, rule by rule? |
| [Design](03-design.md) | How does it decide, and how do we check it? |
| [Architecture](04-architecture.md) | What are the parts and how does a call flow through them? |
| [Decisions](adr/) | What did we pick, what did we turn down, and why? |
| [Experiments](05-experiments.md) | What did we measure before deciding? |
