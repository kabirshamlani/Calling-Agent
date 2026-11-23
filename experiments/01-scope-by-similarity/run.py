"""Can a similarity score decide whether a question is in scope?

The common shortcut: embed the question, find the closest FAQ chunk, and call
it in scope if the score clears a threshold. This script measures how well that
separates the `answer` cases from the `handoff` cases in evals/cases.yaml,
using a dense embedding model and BM25.

Run: uv run --with fastembed --with rank-bm25 --with pyyaml --with numpy \
         experiments/01-scope-by-similarity/run.py
"""

import re
from pathlib import Path

import numpy as np
import yaml
from fastembed import TextEmbedding
from rank_bm25 import BM25Okapi

ROOT = Path(__file__).resolve().parents[2]


def load_chunks() -> list[str]:
    """Split each article at its headings. The title stays on every chunk."""
    chunks = []
    for path in sorted((ROOT / "data/faq").glob("*.md")):
        body = path.read_text().split("---", 2)[2]
        title = re.search(r"^# (.+)$", body, re.MULTILINE).group(1)
        for section in re.split(r"\n(?=#{2,4} )", body):
            text = section.strip()
            if len(text.split()) > 5:
                chunks.append(f"{title}\n{text}")
    return chunks


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def auc(positives: np.ndarray, negatives: np.ndarray) -> float:
    """Chance that a random in-scope case outscores a random out-of-scope one."""
    wins = (positives[:, None] > negatives[None, :]).mean()
    ties = (positives[:, None] == negatives[None, :]).mean()
    return float(wins + ties / 2)


def best_threshold(positives: np.ndarray, negatives: np.ndarray) -> tuple[float, float, int, int]:
    """Threshold with the highest accuracy, and the errors it still makes."""
    best = (0.0, 0.0, 0, 0)
    for threshold in np.unique(np.concatenate([positives, negatives])):
        false_rejects = int((positives < threshold).sum())
        false_accepts = int((negatives >= threshold).sum())
        accuracy = 1 - (false_rejects + false_accepts) / (len(positives) + len(negatives))
        if accuracy > best[1]:
            best = (float(threshold), accuracy, false_accepts, false_rejects)
    return best


def report(name: str, scores: np.ndarray, cases: list[dict]) -> None:
    in_scope = np.array([s for s, c in zip(scores, cases, strict=True) if c["expect"] == "answer"])
    out_scope = np.array([s for s, c in zip(scores, cases, strict=True) if c["expect"] == "handoff"])
    threshold, accuracy, false_accepts, false_rejects = best_threshold(in_scope, out_scope)
    print(f"\n{name}")
    print(f"  AUC {auc(in_scope, out_scope):.3f}")
    print(
        f"  best threshold {threshold:.3f}: accuracy {accuracy:.1%}, "
        f"{false_accepts} wrongly answered, {false_rejects} wrongly handed off"
    )
    strict = out_scope.max()
    lost = int((in_scope <= strict).sum())
    print(
        f"  to answer nothing out of scope, the threshold must exceed {strict:.3f}; "
        f"that hands off {lost} of {len(in_scope)} valid questions"
    )
    ranked = sorted(zip(scores, cases, strict=True), key=lambda pair: -pair[0])
    print("  highest-scoring out-of-scope questions:")
    for score, case in [p for p in ranked if p[1]["expect"] == "handoff"][:6]:
        print(f"    {score:.3f}  {case['say']}")
    print("  lowest-scoring in-scope questions:")
    for score, case in [p for p in ranked if p[1]["expect"] == "answer"][-4:]:
        print(f"    {score:.3f}  {case['say']}")


def main() -> None:
    cases = [
        c
        for c in yaml.safe_load((ROOT / "evals/cases.yaml").read_text())
        if c["expect"] in ("answer", "handoff")
    ]
    chunks = load_chunks()
    questions = [c["say"] for c in cases]
    print(
        f"{len(chunks)} FAQ chunks, {len(cases)} questions "
        f"({sum(c['expect'] == 'answer' for c in cases)} in scope)"
    )

    model = TextEmbedding("BAAI/bge-small-en-v1.5")
    chunk_vectors = np.array(list(model.embed(chunks)))
    question_vectors = np.array(list(model.query_embed(questions)))
    report(
        "Dense embeddings (bge-small-en-v1.5), max cosine similarity",
        (question_vectors @ chunk_vectors.T).max(axis=1),
        cases,
    )

    bm25 = BM25Okapi([tokens(c) for c in chunks])
    report("BM25, max score", np.array([bm25.get_scores(tokens(q)).max() for q in questions]), cases)


if __name__ == "__main__":
    main()
