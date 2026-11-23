"""The test sets have rules of their own. Break one and the evals quietly mean less."""

import re
from pathlib import Path

import pytest
import yaml

from helpline.gate import unsupported_numbers
from helpline.prompt import RULES, load_articles

EVALS = Path(__file__).parents[1] / "evals"
ACTIONS = {"answer", "handoff", "chat", "unclear", "end"}
ARTICLES = load_articles()
PROMPT_EXAMPLES = {
    line.removeprefix("caller: ") for line in RULES.lower().splitlines() if line.startswith("caller: ")
}


def load(name: str) -> list[dict]:
    return yaml.safe_load((EVALS / name).read_text())


@pytest.mark.parametrize("name", ["cases.yaml", "holdout.yaml"])
def test_single_question_sets_are_well_formed(name):
    cases = load(name)
    assert len({c["id"] for c in cases}) == len(cases)
    for case in cases:
        assert case["expect"] in ACTIONS, case["id"]
        if case["expect"] == "answer":
            assert set(case["article"]) <= set(ARTICLES), case["id"]


def test_conversations_only_allow_known_actions():
    for call in load("conversations.yaml"):
        for step in call["turns"]:
            assert set(step["allow"]) <= ACTIONS, call["name"]


def test_no_test_question_is_also_a_prompt_example():
    # A question the model has been shown the answer to tests nothing.
    asked = [c["say"] for name in ("cases.yaml", "holdout.yaml") for c in load(name)]
    asked += [step["say"] for call in load("conversations.yaml") for step in call["turns"]]
    assert not [say for say in asked if say.lower().strip(" .?!") in PROMPT_EXAMPLES]


def test_the_prompt_examples_obey_the_number_rule():
    examples = re.findall(r"^\[answer:(\d\d)\] (.+)$", RULES, re.MULTILINE)
    assert examples
    for article_id, answer in examples:
        assert not unsupported_numbers(answer, ARTICLES[article_id].text), answer
