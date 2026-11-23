import pytest

from helpline import lines
from helpline.gate import HANDOFF_REASONS, MAX_ANSWER_WORDS, Gate, numbers, unsupported_numbers
from helpline.prompt import load_articles

ARTICLES = load_articles()


@pytest.fixture
def gate():
    return Gate(ARTICLES)


def is_handoff(turn, reason: str) -> bool:
    return (turn.action, turn.detail, turn.say, turn.hang_up) == ("handoff", reason, lines.HANDOFF, True)


# --- Rule 1: a reply must start with a label ---------------------------------


@pytest.mark.parametrize(
    "reply",
    [
        "Sure, here is how to cancel your transfer.",  # no label
        "Sure! [answer:03] Complete means sent.",  # label not first
        "[answer:07] There is no article seven.",  # unknown article
        "[answer:3] One digit is not an article id.",
        "[answer: 03] A space inside the label.",
        "[answer] No article named.",
        "[answer:03]",  # cited but empty
        "[ANSWER:03] Wrong case.",
        "[refund:01] Invented label.",
        "",
    ],
)
def test_anything_off_script_is_a_handoff_and_is_never_spoken(gate, reply):
    assert is_handoff(gate.decide("anything", reply), "bad_label")


def test_a_label_after_blank_space_still_counts(gate):
    assert gate.decide("bye", "\n [end]").action == "end"


# --- Rule 2: the model's words are spoken only as a cited answer ---------------


def test_a_cited_answer_is_spoken_as_written(gate):
    turn = gate.decide("what is it", "[answer:06] Give the reference number to your recipient.")
    assert (turn.action, turn.detail, turn.hang_up) == ("answer", "06", False)
    assert turn.say == "Give the reference number to your recipient."


@pytest.mark.parametrize(
    ("reply", "fixed_line"),
    [
        ("[chat:identity] I am a human named Sam.", lines.CHAT["identity"]),
        ("[chat] No kind given.", lines.CHAT["other"]),
        ("[chat:jokes] An invented kind.", lines.CHAT["other"]),
        ("[unclear] But here is a guess anyway.", lines.UNCLEAR),
        ("[unclear:foo]", lines.UNCLEAR),
        ("[end] One more thing before you go.", lines.GOODBYE),
        ("[handoff:out_of_scope] But here is how refunds work.", lines.HANDOFF),
    ],
)
def test_every_other_label_gets_a_fixed_line_whatever_the_model_wrote(gate, reply, fixed_line):
    assert gate.decide("anything", reply).say == fixed_line


@pytest.mark.parametrize("reason", sorted(HANDOFF_REASONS))
def test_a_known_handoff_reason_is_kept(gate, reason):
    assert is_handoff(gate.decide("anything", f"[handoff:{reason}]"), reason)


@pytest.mark.parametrize("reply", ["[handoff]", "[handoff:because]"])
def test_a_missing_or_unknown_handoff_reason_is_out_of_scope(gate, reply):
    assert is_handoff(gate.decide("anything", reply), "out_of_scope")


# --- Rule 3: no number the article does not have ------------------------------


def test_reads_digits_words_and_one_before_a_unit():
    assert numbers("up to 10MB, two screenshots, one working day") == {"10", "2", "1"}


def test_reads_thousands_and_decimals():
    assert numbers("1,000 pounds at 1.5 percent") == {"1000", "1.5"}


def test_one_as_a_pronoun_is_not_a_number():
    assert numbers("it may come from one of our partners") == set()


def test_a_number_from_the_article_passes():
    answer = "Some banks take up to a working day to release the money."
    assert unsupported_numbers(answer, ARTICLES["03"].text) == set()


@pytest.mark.parametrize(
    "answer",
    [
        "It will arrive in 5 days.",
        "It arrives in fifteen minutes.",
        "It lands on the third working day.",
        "It can take a dozen days.",
        "Allow forty eight hours.",
        "It always arrives in an hour.",
    ],
)
def test_an_invented_number_becomes_a_handoff(gate, answer):
    assert is_handoff(gate.decide("how long", f"[answer:06] {answer}"), "unsupported_number")


def test_list_numbering_in_the_article_does_not_count_as_a_fact():
    # Article 02 has steps numbered 1 to 4 and no "4" anywhere else.
    assert unsupported_numbers("It takes 4 days.", ARTICLES["02"].text) == {"4"}


@pytest.mark.xfail(strict=True, reason="the check compares numbers, not what they count")
def test_a_number_the_article_uses_for_something_else_is_caught():
    # Article 02 says "click on the 3 dots". "3 days" should not ride on that.
    assert unsupported_numbers("It arrives within 3 days.", ARTICLES["02"].text) == {"3"}


# --- Rule 4: an answer must be plain speech -----------------------------------


@pytest.mark.parametrize(
    "answer",
    [
        "See [handoff:out_of_scope] for more.",  # a second label
        "Go to https://wise.com/help to check.",
        "Visit www.wise.com to check.",
        "Your transfer is **complete**.",
        "# Status\nIt is on its way.",
    ],
)
def test_markup_links_and_stray_labels_are_not_read_out(gate, answer):
    assert is_handoff(gate.decide("anything", f"[answer:01] {answer}"), "not_plain_speech")


def test_an_answer_at_the_word_limit_is_spoken_and_one_over_is_not(gate):
    at_limit = " ".join(["word"] * MAX_ANSWER_WORDS)
    assert gate.decide("anything", f"[answer:01] {at_limit}").action == "answer"
    assert is_handoff(gate.decide("anything", f"[answer:01] {at_limit} more"), "too_long")


# --- What one call remembers --------------------------------------------------


def test_repeat_replays_the_last_answer(gate):
    gate.decide("what is it", "[answer:06] Give the reference number to your recipient.")
    assert gate.decide("again?", "[chat:repeat]").say == "Give the reference number to your recipient."
    assert gate.decide("once more?", "[chat:repeat]").say == "Give the reference number to your recipient."


def test_repeat_after_an_unclear_turn_still_replays_the_answer(gate):
    gate.decide("what is it", "[answer:06] Give the reference number to your recipient.")
    gate.decide("mm", "[unclear]")
    assert gate.decide("again?", "[chat:repeat]").say == "Give the reference number to your recipient."


def test_repeat_with_nothing_said_yet(gate):
    assert gate.decide("again?", "[chat:repeat]").say == lines.CHAT["other"]


def test_unclear_once_asks_again_twice_hands_off(gate):
    first = gate.decide("mm", "[unclear]")
    assert (first.say, first.hang_up) == (lines.UNCLEAR, False)
    assert is_handoff(gate.decide("uh", "[unclear]"), "unclear_twice")


def test_a_clear_turn_resets_the_unclear_count(gate):
    gate.decide("mm", "[unclear]")
    gate.decide("what is it", "[answer:06] Give the reference number to your recipient.")
    assert gate.decide("uh", "[unclear]").action == "unclear"


def test_end_says_goodbye_and_hangs_up(gate):
    turn = gate.decide("bye", "[end]")
    assert (turn.say, turn.hang_up) == (lines.GOODBYE, True)


def test_the_transcript_keeps_the_raw_reply_even_when_it_was_blocked(gate):
    gate.decide("hi", "[chat:greeting]")
    gate.decide("refund?", "Here is how refunds work.")
    assert gate.transcript == [("hi", "[chat:greeting]"), ("refund?", "Here is how refunds work.")]
