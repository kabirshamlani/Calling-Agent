.PHONY: test lint eval holdout conversations talk serve web call faq

# Unit tests. No keys needed.
test:
	uv run pytest -q

lint:
	uv run ruff check . && uv run ruff format --check .

# The main question set through the model and the gate.
eval:
	uv run python evals/run.py --runs 3

# The questions the prompt was never tuned on.
holdout:
	uv run python evals/run.py --set holdout --runs 3

# Whole calls with edge cases, in text.
conversations:
	uv run python evals/run_conversations.py

# Talk to the agent from this terminal.
talk:
	uv run python -m helpline.agent console

# Answer calls from the phone number and the website.
serve:
	uv run python -m helpline.agent dev

# The website: http://localhost:8787
web:
	uv run python web/server.py

# A scripted call with real audio. macOS only; the agent must be serving.
call:
	uv run python scripts/test_call.py "What is a proof of payment?" "How do I cancel my transfer?"

# Download the six articles again.
faq:
	uv run python scripts/fetch_faq.py
