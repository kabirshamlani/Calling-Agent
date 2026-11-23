"""Run test questions through the model and the gate, and score the result.

Each case is one caller sentence on a fresh call. The reply goes through the
same code a live call uses, so a pass here means the caller would have heard
the right thing.

Usage: uv run python evals/run.py [--set cases|holdout] [--models MODEL ...] [--runs N]
Writes evals/results/<set>--<model>.json and prints a summary.
"""

import argparse
import asyncio
import json
import statistics
import time
from collections import Counter
from datetime import date
from pathlib import Path

import yaml
from dotenv import load_dotenv

from helpline.brain import MODEL, make_llm, respond
from helpline.gate import Gate, Turn
from helpline.prompt import build_system_prompt, load_articles, prompt_version

HERE = Path(__file__).parent
SECONDS_BETWEEN_REQUESTS = 4.5  # the free model tier allows 15 requests a minute


def problems_with(case: dict, turn: Turn) -> list[str]:
    """Reasons this case failed. Empty means it passed."""
    if turn.action != case["expect"]:
        why = f" ({turn.detail})" if turn.detail else ""
        return [f"expected {case['expect']}, got {turn.action}{why}"]
    if turn.action != "answer":
        return []
    said = turn.say.lower()
    found = []
    if turn.detail not in case["article"]:
        found.append(f"cited article {turn.detail}, expected {' or '.join(case['article'])}")
    found += [f"missing '{fact}'" for fact in case.get("must_say", []) if fact.lower() not in said]
    found += [f"said '{bad}'" for bad in case.get("must_not_say", []) if bad.lower() in said]
    return found


async def run_case(case: dict, llm, system_prompt: str, articles: dict) -> dict:
    started = time.perf_counter()
    reply, turn = await respond([llm], system_prompt, Gate(articles), case["say"])
    return {
        "id": case["id"],
        "say": case["say"],
        "expect": case["expect"],
        "got": turn.action,
        "detail": turn.detail,
        "reply": reply,
        "problems": problems_with(case, turn),
        "seconds": round(time.perf_counter() - started, 2),
    }


def summarise(model: str, runs: list[list[dict]], version: str) -> dict:
    rows = [row for run in runs for row in run]
    by_case: dict[str, list[dict]] = {}
    for row in rows:
        by_case.setdefault(row["id"], []).append(row)
    should_not_answer = [r for r in rows if r["expect"] != "answer"]
    should_answer = [r for r in rows if r["expect"] == "answer"]
    times = [r["seconds"] for r in rows]
    return {
        "model": model,
        "date": date.today().isoformat(),
        "prompt_version": version,
        "runs": len(runs),
        "cases": len(by_case),
        "cases_passing_every_run": sum(all(not r["problems"] for r in rs) for rs in by_case.values()),
        "wrongly_answered": sum(r["got"] == "answer" for r in should_not_answer),
        "of_non_answer_attempts": len(should_not_answer),
        "wrongly_handed_off": sum(r["got"] == "handoff" for r in should_answer),
        "of_answer_attempts": len(should_answer),
        "model_errors": sum(r["detail"] == "model_error" for r in rows),
        "unstable_cases": sorted(i for i, rs in by_case.items() if len({r["got"] for r in rs}) > 1),
        "confusion": dict(Counter(f"{r['expect']} -> {r['got']}" for r in rows)),
        "seconds_median": statistics.median(times),
        "seconds_p95": round(statistics.quantiles(times, n=20)[-1], 2),
        "failures": [r for r in rows if r["problems"]],
    }


async def evaluate(model: str, runs: int, cases: list[dict]) -> dict:
    articles = load_articles()
    system_prompt = build_system_prompt(articles)
    llm = make_llm(model)
    results = []
    try:
        for _ in range(runs):
            run = []
            for case in cases:
                run.append(await run_case(case, llm, system_prompt, articles))
                await asyncio.sleep(SECONDS_BETWEEN_REQUESTS)
            results.append(run)
    finally:
        await llm.aclose()
    return summarise(model, results, prompt_version(system_prompt))


def show(summary: dict) -> None:
    print(f"\n{summary['model']}  ({summary['runs']} run(s), prompt {summary['prompt_version']})")
    print(f"  cases passing every run: {summary['cases_passing_every_run']} of {summary['cases']}")
    print(f"  wrongly answered:        {summary['wrongly_answered']} of {summary['of_non_answer_attempts']}")
    print(f"  wrongly handed off:      {summary['wrongly_handed_off']} of {summary['of_answer_attempts']}")
    print(f"  model errors:            {summary['model_errors']}")
    print(f"  reply time:              median {summary['seconds_median']}s, p95 {summary['seconds_p95']}s")
    for failure in summary["failures"]:
        print(f"    {failure['id']:11} {'; '.join(failure['problems'])}")
        print(f"                {failure['say'][:70]!r} -> {failure['reply'][:90]!r}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", default=[MODEL])
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--set", default="cases", choices=["cases", "holdout"])
    args = parser.parse_args()

    load_dotenv(HERE.parent / ".env")
    cases = yaml.safe_load((HERE / f"{args.set}.yaml").read_text())
    (HERE / "results").mkdir(exist_ok=True)
    for model in args.models:
        summary = await evaluate(model, args.runs, cases)
        (HERE / "results" / f"{args.set}--{model}.json").write_text(json.dumps(summary, indent=2))
        show(summary)


if __name__ == "__main__":
    asyncio.run(main())
