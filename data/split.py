"""Benchmark Question Splitter for Development (30%) and Final Evaluation (70%)."""

import argparse
import json
import random
from pathlib import Path
from typing import Any


def split_questions(
    questions: list[dict[str, Any]],
    dev_ratio: float = 0.30,
    seed: int = 42,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Splits questions deterministically using a fixed random seed.

    Returns:
        (dev_split, test_split)
    """
    rng = random.Random(seed)
    shuffled = list(questions)
    rng.shuffle(shuffled)

    dev_count = int(len(shuffled) * dev_ratio)
    dev_split = shuffled[:dev_count]
    test_split = shuffled[dev_count:]

    return dev_split, test_split


def create_and_save_splits(
    input_file: Path,
    output_dir: Path,
    dev_ratio: float = 0.30,
    seed: int = 42,
) -> tuple[Path, Path]:
    """Reads input questions, creates 30/70 split, and writes them to output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)
    questions = json.loads(input_file.read_text(encoding="utf-8"))

    dev_split, test_split = split_questions(questions, dev_ratio=dev_ratio, seed=seed)

    dev_path = output_dir / f"dev_split_{int(dev_ratio * 100)}.json"
    test_path = output_dir / f"test_split_{int((1 - dev_ratio) * 100)}.json"

    dev_path.write_text(json.dumps(dev_split, indent=2), encoding="utf-8")
    test_path.write_text(json.dumps(test_split, indent=2), encoding="utf-8")

    print(f"Created splits from {len(questions)} questions (seed={seed}):")
    print(f"  Dev Split  ({len(dev_split)} questions) -> {dev_path}")
    print(f"  Test Split ({len(test_split)} questions) -> {test_path}")

    return dev_path, test_path


def main():
    parser = argparse.ArgumentParser(description="Create 30/70 dev/test split for BIRD/Spider")
    parser.add_argument(
        "--input", type=str, required=True, help="Path to input questions JSON file"
    )
    parser.add_argument("--outdir", type=str, default="./data/benchmarks", help="Output directory")
    parser.add_argument("--seed", type=int, default=42, help="Fixed random seed")
    parser.add_argument(
        "--dev-ratio", type=float, default=0.30, help="Development split ratio (default: 0.30)"
    )

    args = parser.parse_args()
    create_and_save_splits(
        input_file=Path(args.input),
        output_dir=Path(args.outdir),
        dev_ratio=args.dev_ratio,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
