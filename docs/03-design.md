# Design

How the agent decides what to do, and how we check that it decides well. The [spec](02-spec.md) says what it must do. The [architecture doc](04-architecture.md) covers the audio plumbing.

## The idea in one paragraph

The language model reads the six articles and the caller's words, and writes a reply that starts with a label. The label says which of five actions it chose. Our code reads the label before a single word is spoken, and the code, not the model, carries out the action.

The model's own words reach the caller in one case only: an answer that names the article it came from. Everything else the caller hears is a fixed line picked by the code. If the label is missing or wrong, the code hands off.

A rule that lives only in a prompt can be talked around. So the prompt asks for the right behaviour, and the code refuses to speak anything else.

## The label

Every model reply starts with one label in square brackets.

| Label | Meaning | What the code does |
| --- | --- | --- |
| `[answer:02]` | The answer is in article 02 | Checks the text, then speaks it. Logs the article. |
| `[chat:kind]` | Greeting, "say that again", "are you a robot?", no question yet | Speaks the fixed line for that kind. For `repeat`, replays the last thing it said. |
| `[unclear]` | Could not make out a question | Speaks the fixed "didn't catch that" line. Second time in a row, hands off. |
| `[handoff:reason]` | Not covered, or needs a person | Speaks the fixed handoff line. Hangs up. |
| `[end]` | The caller is done | Speaks the fixed goodbye line. Hangs up. |

Chat kinds: `greeting`, `repeat`, `identity`, `wait`, `other`.
Handoff reasons: `out_of_scope`, `account_lookup`, `asked_for_human`, `needs_human`, `rule_bending`, `other_language`.

Any text the model writes after a `chat`, `unclear`, `handoff` or `end` label is thrown away.

Example:

```
Caller: It says complete but my brother hasn't got it.
Model:  [answer:03] Complete means we've sent the money to his bank. Some banks
        take up to one working day to release it. He can ask his bank to speed
        it up with the transfer receipt. Want to know how to get the receipt?

Caller: How do I cancel it?
Model:  [handoff:out_of_scope]
Code:   speaks the handoff line, waits for it to finish, hangs up.
```

Three things this buys us:

1. **The decision comes before any sound.** The code waits for the whole reply, which is at most a few sentences, and checks it before a word is spoken. There is no moment where the agent begins an answer and then changes its mind. Waiting costs time: see [where the time goes](04-architecture.md#where-the-time-goes).
2. **No citation, no answer.** An answer has to name its article. If the label is missing, misspelled, or names an article that does not exist, the code treats it as a handoff. Unlabelled text is never spoken. A caller who talks the model into going off-script gets, at worst, a fixed line.
3. **Every turn is a typed record.** Action, article, reason. The log and the evals read the same value the code acted on.

We looked at three other ways to make this decision: a separate classifier before the answer, a tool call, and a JSON reply. [ADR 0004](adr/0004-scope-decision-as-a-label.md) has the comparison.

## The number check

One more check sits between an answer and the voice. Before an answer is spoken, the code pulls out every number in it ("2 working days", "10MB", "pacs.008") and looks for it in the cited article. If a number is not there, the answer is not spoken and the call is handed off.

Numbers spelled out count too: "two" matches "2", and "fifteen", "forty", "a dozen" and "the third day" are all read as quantities.

A made-up number is the most damaging thing this agent could say: a delivery time, a fee, a limit. This check catches most of them in microseconds, with no second model.

It has two gaps, and tests mark both. It compares numbers, not what they count: article 02 says "click on the 3 dots", so "3 days" would pass against article 02. And it reads "twenty four" as 20 and 4, not 24.

## The plain-speech check

An answer is also blocked if it would not survive being read aloud: a web address, markdown symbols, a second label tucked inside it, or more than 60 words. The prompt asks for 45 words. Sixty is where the code refuses.

## The prompt

One system prompt, in four parts, in this order:

1. **Role and limits.** You answer phone calls about where a transfer is. You only know what is in the articles below. You cannot see accounts.
2. **The five labels**, when to use each, and worked examples. The examples lean on the hard cases: near-scope questions, account lookups, attempts to change the rules. No example reuses a test question, and a unit test enforces that. A model that has seen the answer is not being tested.
3. **How to speak.** Two or three sentences. Plain words. No lists, no web addresses. Say "the app" instead of reading out click paths. End an answer with a short offer when there is more.
4. **The six articles**, in full, each with its number.

The articles go last and never change, so the provider can cache the whole prefix. The caller's words go in as a user message. Text from the caller is data to sort. The prompt says so, and the `inj-` test cases check it.

### Why the whole articles and not search

The six articles are 2,300 words, about 3,500 tokens. That fits in the prompt many times over. Search would add a step that can fetch the wrong passage, and the articles overlap enough that it often would. We also tested whether a search score could decide scope. It cannot: see [experiment 01](05-experiments.md#01-can-a-similarity-score-decide-scope). Details in [ADR 0003](adr/0003-whole-faq-in-the-prompt.md).

## From page to speech

The articles were written to be read. Article 02 alone takes over four minutes to read aloud. So the model rewrites as it answers: main point first, short sentences, and an offer of more. The risk in rewriting is drift, where the spoken answer says something the article does not. Two things guard against that today:

- The prompt forbids adding facts, numbers or promises, and forbids saying anything about the caller's own transfer.
- The number check above blocks invented figures during the call.

A third, a judge that compares every answer with its article, is designed but not built ([Check 2](#check-2-are-the-answers-true-to-the-articles) below).

## What the code owns

The model never controls these.

| Thing | Owned by code because |
| --- | --- |
| Greeting, handoff, goodbye, "didn't catch that" and small-talk lines | They must be the same on every call, and no caller can change them |
| The number check on answers | A check in code cannot be argued with |
| Hanging up | It has to wait for the last line to finish playing |
| Counting unclear turns and silence | A counter is more reliable than asking a model to remember |
| Ignoring the caller during the handoff line | A handoff is final (R17) |
| Falling back to handoff on any error | When in doubt, hand off |

## Where the logic lives

```
src/helpline/
  lines.py     every fixed line the agent can say
  prompt.py    loads the six articles and builds the system prompt
  gate.py      label parser, number check, per-call memory. Decides what is said.
  brain.py     skips the model when a rule is enough; otherwise asks it, then a backup
  agent.py     the phone call: greeting, speaking, silence, hang-up, call log
```

About 700 lines in all. `gate.py` is plain Python with no audio and no network. The evals and the live call both go through the same two functions in `brain.py`, `draft()` and `judge()`, with the same five-second limit per model, so what we test in text is what runs on the phone.

## How we check it

Four checks, cheapest first. The first three each run from one `make` command and write their results to `evals/results/`.

### Check 1: does it pick the right action?

Run all 78 cases in [`evals/cases.yaml`](../evals/cases.yaml) through the model and the gate as text. Compare the action to the expected one. Each case runs three times, because a model that is right two times out of three is not right.

The prompt was tuned on those 78. So there is a second set, [`evals/holdout.yaml`](../evals/holdout.yaml), of 30 questions written afterwards and never used for tuning. That set is the honest score.

The report is a table of expected against actual, plus two headline numbers:

- **Wrongly answered:** out-of-scope questions that got an answer. Target 0.
- **Wrongly handed off:** in-scope questions that got a handoff. Target under 5%.

We report them separately. Folding them into one accuracy figure would hide the one that matters.

### Check 2: are the answers true to the articles?

For every `answer` case:

- **Plain checks.** The reply contains the `must_say` facts, none of the `must_not_say` ones, and cites an expected article. Length and markup are checked by the gate itself.
- **Judge.** A second model, from a different provider than the one answering, gets the cited article and the reply. It lists each claim in the reply and marks whether the article supports it. Any unsupported claim fails the case. A model grading its own family's work tends to share its blind spots.

A judge can be wrong too. Before trusting it, we hand-label 20 replies and confirm the judge agrees.

The plain checks are built. The judge is not built yet.

### Check 3: does it hold up over a whole call?

Two ways. In text, [`evals/conversations.yaml`](../evals/conversations.yaml) plays 16 whole calls through the gate with its memory intact: follow-ups that drift out of scope, rule-bending after normal answers, a caller in trouble. With real audio, [`scripts/test_call.py`](../scripts/test_call.py) joins as a caller, speaks with a computer voice, can stay silent or talk over an answer, and reports when the agent replied and whether it ended the call.

### Check 4: does it work on a real phone?

The acceptance checks in the [spec](02-spec.md#acceptance-checks), run by hand on a real call. Text tests cannot tell you whether the last word of the handoff line got cut off. Two real phone calls have been made so far. The first found a bug no other test could: the agent greeted the caller while the line was still ringing.

### Plain unit tests

No model involved: every path through the gate, the number and plain-speech checks, the article loader, and the test sets themselves (unique ids, known actions, no question that is also a prompt example).

## What this design does not do

- **It does not fully check answers live.** The label, number and plain-speech checks run on every turn. The judge in Check 2 runs offline, because running it live would add about a second of silence. So an answer that cites a real article, contains no new number, and still misstates the article would be spoken. The offline judge is how we find out how often that happens.
- **It does not understand a caller that speech recognition mangles badly.** It asks once, then hands off.
- **It trusts one model's judgement on scope.** The code makes sure an answer is labelled, cited and free of new numbers. Whether the question was truly covered is the model's call. If it is wrong, nothing catches it during the call. That is why Check 1 exists and why its target is zero.
