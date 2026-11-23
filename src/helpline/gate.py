"""The gate between the model and the voice.

The model proposes a reply. This module decides what is actually said and
whether the call ends. It is plain Python: no audio, no network. The evals and
the live call both go through it.

Four rules:
  1. A reply must start with a label. Anything else is a handoff.
  2. The model's own words are spoken only as an answer that cites a real article.
  3. An answer may not contain a number its article does not have.
  4. An answer must be plain speech: no markup, no links, no second label, not too long.

What it cannot check is whether the cited article really supports the answer's
meaning. That is the model's judgement, and the evals measure it.
"""

import re
from dataclasses import dataclass, field
from typing import Literal

from helpline import lines
from helpline.prompt import Article

Action = Literal["answer", "chat", "unclear", "handoff", "end"]

HANDOFF_REASONS = {
    "out_of_scope",
    "account_lookup",
    "asked_for_human",
    "needs_human",
    "rule_bending",
    "other_language",
}
MAX_UNCLEAR_IN_A_ROW = 2
MAX_ANSWER_WORDS = 60  # the prompt asks for 45; this is the point where we refuse to read it out
LABEL = re.compile(r"\s*\[(answer|chat|unclear|handoff|end)(?::([a-z0-9_]+))?\]\s*(.*)", re.DOTALL)
NOT_SPEECH = re.compile(r"[\[\]*#]|https?:|www\.")  # a second label, markdown, a web address

NUMBER_WORDS = {
    "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8",
    "nine": "9", "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13", "fourteen": "14",
    "fifteen": "15", "sixteen": "16", "seventeen": "17", "eighteen": "18", "nineteen": "19",
    "twenty": "20", "thirty": "30", "forty": "40", "fifty": "50", "sixty": "60", "seventy": "70",
    "eighty": "80", "ninety": "90", "hundred": "100", "thousand": "1000", "million": "1000000",
}  # fmt: skip
# Quantities with no digit form. They must appear in the article as the same word.
QUANTITY_WORDS = {"half", "dozen", "couple", "third", "fourth", "fifth", "sixth", "seventh",
                  "eighth", "ninth", "tenth"}  # fmt: skip
UNITS = (
    r"(?:working |business |calendar )?"
    r"(?:second|minute|hour|day|week|month|year|percent|dollar|pound|euro|rupee|file|screenshot)s?"
)
# "one" and "a" are mostly not numbers ("one of our partners"). They count
# only in front of a unit: "one working day", "an hour".
ONE_UNIT = re.compile(rf"\b(?:one|an?)\s+{UNITS}\b")
DIGITS = re.compile(r"\d+(?:[.,]\d+)*")
WORDS = re.compile(r"[a-z]+")
LIST_MARKER = re.compile(r"^\s*(?:#+\s*)?\d+\.\s", re.MULTILINE)  # "1. Log in" is numbering


@dataclass(frozen=True)
class Turn:
    action: Action
    detail: str | None  # article id, chat kind, or the reason for a handoff
    say: str
    hang_up: bool = False


def numbers(text: str) -> set[str]:
    """Every quantity in the text, in one spelling: "two" and "2" both come back as "2"."""
    text = text.lower()
    found = {match.replace(",", "") for match in DIGITS.findall(text)}
    for word in WORDS.findall(text):
        if word in NUMBER_WORDS:
            found.add(NUMBER_WORDS[word])
        elif word in QUANTITY_WORDS:
            found.add(word)
    if ONE_UNIT.search(text):
        found.add("1")
    return found


def unsupported_numbers(answer: str, article_text: str) -> set[str]:
    """Quantities the answer states that the article never does."""
    return numbers(answer) - numbers(LIST_MARKER.sub("", article_text))


def handoff(reason: str) -> Turn:
    return Turn("handoff", reason, lines.HANDOFF, hang_up=True)


@dataclass
class Gate:
    """One per call."""

    articles: dict[str, Article]
    transcript: list[tuple[str, str]] = field(default_factory=list)  # (heard, model reply)
    unclear_in_a_row: int = 0
    last_said: str | None = None

    def decide(self, heard: str, model_reply: str) -> Turn:
        turn = self._judge(model_reply)
        self.transcript.append((heard, model_reply))
        self.unclear_in_a_row = self.unclear_in_a_row + 1 if turn.action == "unclear" else 0
        if turn.action in ("answer", "chat") and turn.detail != "repeat":
            self.last_said = turn.say
        return turn

    def _judge(self, model_reply: str) -> Turn:
        match = LABEL.fullmatch(model_reply)
        if not match:
            return handoff("bad_label")
        action, detail, text = match[1], match[2], match[3].strip()

        if action == "answer":
            return self._judge_answer(detail, text)

        if action == "chat":
            if detail == "repeat":
                return Turn("chat", "repeat", self.last_said or lines.CHAT["other"])
            kind = detail if detail in lines.CHAT else "other"
            return Turn("chat", kind, lines.CHAT[kind])

        if action == "unclear":
            if self.unclear_in_a_row + 1 >= MAX_UNCLEAR_IN_A_ROW:
                return handoff("unclear_twice")
            return Turn("unclear", None, lines.UNCLEAR)

        if action == "end":
            return Turn("end", None, lines.GOODBYE, hang_up=True)

        return handoff(detail if detail in HANDOFF_REASONS else "out_of_scope")

    def _judge_answer(self, article_id: str | None, text: str) -> Turn:
        if article_id not in self.articles or not text:
            return handoff("bad_label")
        if NOT_SPEECH.search(text):
            return handoff("not_plain_speech")
        if len(text.split()) > MAX_ANSWER_WORDS:
            return handoff("too_long")
        if unsupported_numbers(text, self.articles[article_id].text):
            return handoff("unsupported_number")
        return Turn("answer", article_id, text)
