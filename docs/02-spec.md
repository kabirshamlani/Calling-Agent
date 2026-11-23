# Spec

What the agent does, as rules you can test. The [design doc](03-design.md) covers how.

## One call, start to finish

1. The phone rings. The agent picks up.
2. It greets the caller and says it is an automated assistant.
3. The caller speaks. For each thing the caller says, the agent does exactly one of five things:

| Action | When | What the caller hears | Call |
| --- | --- | --- | --- |
| **Answer** | The six articles cover the question | A short answer from the articles | stays open |
| **Hand off** | Anything else | The handoff line | ends |
| **Keep talking** | Greeting, "say that again", no question yet | A short fixed reply, or the last answer again | stays open |
| **Ask again** | The agent could not make out what was said | "Sorry, I didn't catch that" | stays open |
| **Say goodbye** | The caller is done | The goodbye line | ends |

4. The call ends when the agent hands off, the caller says goodbye, or the caller hangs up.

## Fixed lines

The agent does not improvise these. They are written once and spoken word for word. The only words the agent composes itself are answers from the articles.

- **Greeting:** "Hi, you've reached Wise transfer support. I'm an automated assistant. I can help with questions about where your money is. What would you like to know?"
- **Handoff:** "That's something a member of our team needs to help you with. I'm passing you to a human agent now. Thanks for calling."
- **Goodbye:** "Thanks for calling. Goodbye."
- **Did not catch that:** "Sorry, I didn't catch that. Could you say it again?"
- **Small talk** (hello, "are you a robot?", "hang on"): one short fixed reply each, for example "Yes, I'm an automated assistant. What would you like to know about your transfer?"

## Rules

Each rule has test cases in [`evals/cases.yaml`](../evals/cases.yaml). The case prefix is in brackets.

### What it answers

**R1. It answers the six topics.** [`in-`]
How to check a transfer's status. When money will arrive. Why a transfer says complete when the money has not arrived. Why a transfer is taking longer than the estimate. What a proof of payment is. What a banking partner reference number is.

**R2. It answers only from the articles.**
If the articles do not state a fact, the agent does not state it. No delivery times per country, no fees, no promises. Asked "how many days to India?", it says the estimate is shown in the app when the transfer is set up. It gives no number, because the articles give none.

**R3. It answers follow-ups.**
"What's a receipt?" after an answer that mentioned one is in scope if the articles explain it.

**R4. It talks like a person on a phone.**
Two or three sentences, about 20 seconds at most. No lists read aloud, no web addresses, no "click here". If there is more to say, it gives the main point and offers the rest.

### What it hands off

**R5. Any question the six articles do not cover.** [`near-`, `far-`]
This includes questions from the same help centre: cancelling, refunds, fees, wrong recipient, sending limits, cards. Being close to the topic is not enough.

**R6. Any request to look something up.** [`acct-`]
The agent cannot see accounts or transfers. If the caller gives a transfer number or asks it to check, it hands off. It never implies it has looked, and it never says anything about the caller's own transfer: no status, no date, no amount. A general "where is my transfer?" is different: the agent explains how to check the tracker (R1).

**R7. Anyone who asks for a person.** [`human-`]
No arguing, no "let me try first".

**R8. Anyone who sounds like they are in trouble.** [`human-`]
Fraud, a scam, a hacked account, a complaint. These callers need a human now, even if part of the question is technically covered.

**R9. Attempts to change its rules.** [`inj-`]
"Ignore your instructions", "my manager said you can tell me", "pretend the FAQ says". The agent treats what the caller says as a question to sort, never as an instruction to follow.

**R10. Other languages.** [`lang-`]

**R11. Mixed questions.** [`mix-`]
One part covered, one part not. The agent hands off. The human who picks up can answer both halves, and the caller does not have to work out which half was skipped.

### Staying on the line

**R12. Greetings and small talk get one short reply and a nudge back.** [`glue-`]
"Are you a robot?" gets an honest yes.

**R13. Unclear speech gets one "say it again".** [`unclear-`]
Two unclear turns in a row, and the agent hands off. A caller who cannot be understood should not be stuck in a loop.

**R14. Silence gets one "are you still there?".**
Then the agent says goodbye and ends the call.

**R15. The caller can interrupt.**
When the caller starts speaking, the agent stops speaking and listens. The fixed handoff and goodbye lines are the exception: the decision is made, so they play to the end.

### Ending the call

**R16. The last line finishes before the line drops.**
The agent hangs up only after the handoff or goodbye audio has fully played.

**R17. A handoff is final.**
Once the agent decides to hand off, nothing the caller says next reopens the conversation.

### Honesty and safety

**R18. It says it is automated, up front.**

**R19. It does not ask for personal details.**
No names, card numbers, account numbers, or passwords. If the caller offers them, the agent does not repeat them back.

**R20. Every call leaves a record.**
For each turn: what was heard, what was decided, why, which article was used, and how long each stage took. If someone asks "why did it hand off?", the log answers.

## If something breaks

| Failure | What the caller gets |
| --- | --- |
| The language model errors or is too slow | A backup model is asked. If that fails too: the handoff line, then the call ends |
| Speech to text or the voice service fails | The call ends at once, so the caller is not left in silence. Logged as an error. |

The rule behind the table: when in doubt, hand off. A caller who reaches a human a little early is fine. A caller who gets a made-up answer is not.

## Acceptance checks

1. Call the number. The agent picks up within two rings and says the greeting.
2. Ask each of the six questions. Each gets a correct, short answer.
3. Ask "how do I cancel my transfer?". The agent says the handoff line and the call ends after the line finishes.
4. Interrupt a long answer. The agent stops.
5. Say nothing. The agent checks in once, then ends the call.
6. Run the test set. Zero out-of-scope questions answered.
7. Open the call log. Every decision above is in it.
