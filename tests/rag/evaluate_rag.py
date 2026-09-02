#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import Settings  # noqa: E402
from app.services.container import build_container  # noqa: E402


@dataclass(frozen=True, slots=True)
class GoldenCase:
    question: str
    expected_document_title: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate production hybrid retrieval against the 1C golden set."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path(__file__).with_name("rag_golden.json"),
    )
    parser.add_argument("--top-k", type=int, default=3)
    return parser.parse_args()


def normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def load_cases(dataset_path: Path) -> list[GoldenCase]:
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError("Golden dataset must be a non-empty JSON array")
    cases: list[GoldenCase] = []
    for index, raw in enumerate(payload, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"Golden case {index} must be an object")
        question = raw.get("question")
        expected = raw.get("expectedDocumentTitle")
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"Golden case {index} has no question")
        if not isinstance(expected, str) or not expected.strip():
            raise ValueError(f"Golden case {index} has no expectedDocumentTitle")
        cases.append(GoldenCase(question.strip(), expected.strip()))
    return cases


async def evaluate(dataset_path: Path, top_k: int) -> int:
    if top_k < 1:
        raise ValueError("--top-k must be at least 1")
    cases = load_cases(dataset_path)
    settings = Settings()
    container = build_container(settings)
    passed = 0
    try:
        async with container.session_factory() as session:
            for index, case in enumerate(cases, start=1):
                question = case.question
                expected = normalize(case.expected_document_title)
                evidence = await container.rag_service.retrieve(
                    session, question, top_k
                )
                titles = [item.source.title for item in evidence]
                matched = any(
                    expected in normalize(title) or normalize(title) in expected
                    for title in titles
                )
                passed += int(matched)
                status = "OK" if matched else "FAIL"
                print(
                    f"{status} {index:02d}: {question}\n"
                    f"  expected: {case.expected_document_title}\n"
                    f"  retrieved: {titles or ['<empty>']}"
                )
    finally:
        await container.engine.dispose()
    total = len(cases)
    recall = passed / total if total else 0.0
    print(f"\nRecall@{top_k}: {passed}/{total} ({recall:.1%})")
    return 0 if passed == total else 1


def main() -> None:
    args = parse_args()
    raise SystemExit(asyncio.run(evaluate(args.dataset, args.top_k)))


if __name__ == "__main__":
    main()
