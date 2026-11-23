from pathlib import Path

from helpline import lines
from helpline.gate import HANDOFF_REASONS
from helpline.prompt import RULES, build_system_prompt, load_articles

SITE_JS = (Path(__file__).parents[1] / "web" / "site.js").read_text()


def test_six_articles_load_with_their_sources():
    articles = load_articles()
    assert list(articles) == ["01", "02", "03", "04", "05", "06"]
    assert articles["05"].title == "What is a proof of payment?"
    assert all(a.source.startswith("https://wise.com/help/articles/") for a in articles.values())


def test_article_text_has_no_file_header_left_in_it():
    for article in load_articles().values():
        assert "source:" not in article.text and "fetched:" not in article.text


def test_prompt_holds_every_article_after_the_rules():
    articles = load_articles()
    prompt = build_system_prompt(articles)
    assert prompt.startswith(RULES)
    assert all(a.text in prompt for a in articles.values())


def test_every_handoff_reason_and_chat_kind_is_known_to_the_prompt_and_the_website():
    # The gate, the prompt and the site each list these. Add one, and all three must know it.
    for name in [*HANDOFF_REASONS, *lines.CHAT, "repeat"]:
        assert name in RULES, f"{name} is missing from the prompt"
        assert name in SITE_JS, f"{name} is missing from web/site.js"
