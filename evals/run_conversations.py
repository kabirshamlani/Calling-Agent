"""Play whole calls through the model and the gate, and check every turn.

Unlike run.py, the gate keeps its memory across turns here, so this covers
follow-ups, the unclear-turn counter, "say that again", and what happens after
a few normal answers. Audio is not involved.

Usage: uv run python evals/run_conversations.py
"""

import asyncio
import json
from pathlib import Path

import yaml
from dotenv import load_dotenv

from helpline.brain import BACKUP_MODEL, MODEL, make_llm, respond
from helpline.gate import Gate
from helpline.prompt import build_system_prompt, load_articles

HERE = Path(__file__).parent
SECONDS_BETWEEN_REQUESTS = 4.5  # the free model tier allows 15 requests a minute


async def play(call: dict, models: list, system_prompt: str, articles: dict) -> dict:
    gate, turns, problems = Gate(articles), [], []
    for number, step in enumerate(call["turns"], 1):
        reply, turn = await respond(models, system_prompt, gate, step["say"])
        turns.append(
            {
                "heard": step["say"],
                "reply": reply,
                "action": turn.action,
                "detail": turn.detail,
                "said": turn.say,
            }
        )
        if turn.action not in step["allow"]:
            expected = " or ".join(step["allow"])
            problems.append(f"turn {number}: expected {expected}, got {turn.action}")
        for banned in step.get("never_say", []):
            if banned.lower() in turn.say.lower():
                problems.append(f"turn {number}: said '{banned}'")
        if turn.hang_up:
            if number < len(call["turns"]):
                problems.append(f"call ended at turn {number} of {len(call['turns'])}")
            break
        await asyncio.sleep(SECONDS_BETWEEN_REQUESTS)
    return {"name": call["name"], "problems": problems, "turns": turns}


async def main() -> None:
    load_dotenv(HERE.parent / ".env")
    articles = load_articles()
    system_prompt = build_system_prompt(articles)
    calls = yaml.safe_load((HERE / "conversations.yaml").read_text())
    models = [make_llm(MODEL), make_llm(BACKUP_MODEL)]  # the same pair a live call has
    results = []
    try:
        for call in calls:
            results.append(await play(call, models, system_prompt, articles))
            await asyncio.sleep(SECONDS_BETWEEN_REQUESTS)
    finally:
        for model in models:
            await model.aclose()

    for result in results:
        print(f"\n{'PASS' if not result['problems'] else 'FAIL'}  {result['name']}")
        for turn in result["turns"]:
            detail = f":{turn['detail']}" if turn["detail"] else ""
            print(f"    caller: {turn['heard']}")
            print(f"    agent [{turn['action']}{detail}]: {turn['said'][:150]}")
        for problem in result["problems"]:
            print(f"    !! {problem}")
    passed = sum(not r["problems"] for r in results)
    print(f"\n{passed} of {len(results)} calls passed  (models {MODEL}, then {BACKUP_MODEL})")
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "conversations.json").write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
