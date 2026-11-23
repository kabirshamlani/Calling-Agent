import asyncio

import pytest

from helpline import lines
from helpline.brain import respond, same_words, shortcut
from helpline.gate import Gate
from helpline.prompt import load_articles


@pytest.mark.parametrize(
    ("heard", "label"),
    [
        ("Sorry, say that again?", "[chat:repeat]"),
        ("Can you repeat that please?", "[chat:repeat]"),
        ("Pardon?", "[chat:repeat]"),
        ("What did you say?", "[chat:repeat]"),
        ("Agent.", "[handoff:asked_for_human]"),
        ("Representative, please.", "[handoff:asked_for_human]"),
        ("Can I talk to a real person?", "[handoff:asked_for_human]"),
        ("I want to speak to a human.", "[handoff:asked_for_human]"),
        ("Get me a human.", "[handoff:asked_for_human]"),
        ("Hello?", "[chat:greeting]"),
        ("Hi there.", "[chat:greeting]"),
        ("Good morning.", "[chat:greeting]"),
        ("That's all, thanks.", "[end]"),
        ("Okay great, bye.", "[end]"),
        ("No, nothing else.", "[end]"),
        ("Thank you, bye.", "[end]"),
    ],
)
def test_plain_requests_are_decided_without_the_model(heard, label):
    assert shortcut(heard) == label


@pytest.mark.parametrize(
    "heard",
    [
        "Hi, I sent money two days ago and it is not there.",  # a greeting with a question behind it
        "Can I talk to someone about why my transfer is late?",
        "The agent at my bank said to ask you.",
        "Thanks. And what is a proof of payment?",
        "Sorry, I sent it to the wrong person.",
        "Bye the way, when will it arrive?",
        "What is a proof of payment?",
    ],
)
def test_anything_with_more_in_it_goes_to_the_model(heard):
    assert shortcut(heard) is None


class StubModel:
    """Stands in for the language model: replies with what it is told to, or fails."""

    def __init__(self, reply: str | Exception):
        self.reply = reply
        self.requests = 0

    model = "stub"

    def chat(self, chat_ctx, conn_options=None):
        self.requests += 1
        return self

    async def __aenter__(self):
        if isinstance(self.reply, Exception):
            raise self.reply
        return self

    async def __aexit__(self, *_):
        return False

    def __aiter__(self):
        return self._chunks()

    async def _chunks(self):
        yield type("Chunk", (), {"delta": type("Delta", (), {"content": self.reply})})


def turn_for(model: StubModel, heard: str, backup: StubModel | None = None):
    models = [model, backup] if backup else [model]
    return asyncio.run(respond(models, "rules", Gate(load_articles()), heard))


def test_a_shortcut_never_reaches_the_model():
    model = StubModel("[answer:01] should not be used")
    reply, turn = turn_for(model, "Agent.")
    assert (model.requests, reply, turn.detail) == (0, "[handoff:asked_for_human]", "asked_for_human")


def test_a_model_reply_goes_through_the_gate():
    _, turn = turn_for(
        StubModel("[answer:06] Give the reference number to your recipient."), "What is it for?"
    )
    assert (turn.action, turn.say) == ("answer", "Give the reference number to your recipient.")


def test_a_model_that_fails_is_a_handoff():
    reply, turn = turn_for(StubModel(ConnectionError("down")), "What is a proof of payment?")
    assert (reply, turn.detail, turn.say, turn.hang_up) == (
        "(no model answered)",
        "model_error",
        lines.HANDOFF,
        True,
    )


def test_when_the_first_model_fails_the_backup_answers():
    broken, backup = StubModel(ConnectionError("down")), StubModel("[end]")
    _, turn = turn_for(broken, "I think that covers it for me today.", backup)
    assert (broken.requests, backup.requests, turn.action) == (1, 1, "end")


def test_a_model_that_failed_is_not_asked_first_next_time():
    models = [StubModel(ConnectionError("down")), StubModel("[end]")]
    gate = Gate(load_articles())
    for _ in range(2):
        asyncio.run(respond(models, "rules", gate, "I think that covers it for me today."))
    assert [model.requests for model in models] == [2, 1]  # order is now: backup, broken


def test_an_early_draft_is_kept_only_for_the_same_words():
    assert same_words("why is it late?", "Why is it late")
    assert not same_words("Why is it late?", "Why is it late? And can I cancel?")
