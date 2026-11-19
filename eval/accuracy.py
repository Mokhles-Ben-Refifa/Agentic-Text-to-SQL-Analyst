"""Execution Accuracy Evaluator for BIRD Benchmark Datasets.

Compares result sets of generated SQL and gold SQL order-insensitively
and alias-insensitively. Never compares raw SQL strings.
"""

import argparse
import datetime
import json
import logging
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agent.graph import sql_agent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent
BIRD_DB_DIR = ROOT_DIR / "data" / "benchmarks" / "bird"


def normalize_val(val: Any) -> Any:
    """Normalizes an individual SQL cell value for comparison."""
    if val is None:
        return None
    if isinstance(val, float):
        return round(val, 2)
    if isinstance(val, int):
        return val
    s = str(val).strip()
    # Try parsing int/float if formatted as string
    try:
        if "." in s:
            return round(float(s), 2)
        return int(s)
    except (ValueError, TypeError):
        pass
    return s.lower()


def normalize_rows(rows: list[dict[str, Any]] | list[tuple]) -> list[tuple]:
    """Normalizes a list of database rows into sorted tuples of cell values."""
    if not rows:
        return []

    norm_rows = []
    for r in rows:
        if isinstance(r, dict):
            # Sort row values so alias order doesn't fail matching
            vals = tuple(sorted([normalize_val(v) for v in r.values()], key=lambda x: str(x)))
        elif isinstance(r, (list, tuple)):
            vals = tuple(sorted([normalize_val(v) for v in r], key=lambda x: str(x)))
        else:
            vals = (normalize_val(r),)
        norm_rows.append(vals)

    # Sort all rows so row ordering does not fail matching
    return sorted(norm_rows, key=lambda x: str(x))


def compare_result_sets(res_pred: list[dict[str, Any]] | list[tuple], res_gold: list[dict[str, Any]] | list[tuple]) -> bool:
    """Compares two database result sets ignoring row order and column aliases."""
    if len(res_pred) != len(res_gold):
        return False
    if len(res_pred) == 0:
        return True

    pred_norm = normalize_rows(res_pred)
    gold_norm = normalize_rows(res_gold)

    return pred_norm == gold_norm


def run_sqlite_query(db_path: Path, sql: str, timeout: float = 10.0) -> tuple[bool, list[tuple], str | None]:
    """Runs a raw query directly in SQLite with timeout."""
    try:
        conn = sqlite3.connect(str(db_path), timeout=timeout)
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchmany(1000)
        conn.close()
        return True, rows, None
    except Exception as e:
        return False, [], str(e)


def resolve_database_path(db_id: str) -> Path | None:
    """Finds the SQLite database file for a given BIRD database ID."""
    candidate_1 = BIRD_DB_DIR / "financial" / "financial.sqlite"
    if db_id == "financial" and candidate_1.exists():
        return candidate_1

    candidate_2 = BIRD_DB_DIR / "databases" / db_id / f"{db_id}.sqlite"
    if candidate_2.exists():
        return candidate_2

    candidate_3 = BIRD_DB_DIR / db_id / f"{db_id}.sqlite"
    if candidate_3.exists():
        return candidate_3

    return None


def evaluate_sample(
    sample: dict[str, Any],
    thread_id_prefix: str = "eval",
    verbose: bool = False,
) -> dict[str, Any]:
    """Evaluates a single question against the agent and the gold SQL."""
    qid = sample.get("question_id")
    db_id = sample.get("db_id", "financial")
    question = sample.get("question", "")
    evidence = sample.get("evidence", "")
    gold_sql = sample.get("SQL", "")
    difficulty = sample.get("difficulty", "simple")

    db_path = resolve_database_path(db_id)
    if not db_path or not db_path.exists():
        return {
            "question_id": qid,
            "db_id": db_id,
            "difficulty": difficulty,
            "success": False,
            "error": f"Database file not found for db_id: {db_id}",
            "execution_accuracy": False,
        }

    # 1. Run Gold SQL
    gold_ok, gold_rows, gold_err = run_sqlite_query(db_path, gold_sql)
    if not gold_ok:
        logger.warning("Gold SQL failed for QID %s: %s", qid, gold_err)

    # 2. Run Agent
    full_prompt = f"{question} (Evidence: {evidence})" if evidence else question
    state_in = {
        "question": full_prompt,
        "dialect": "sqlite",
        "db_target": str(db_path),
        "max_attempts": 3,
        "attempts": 0,
    }
    config = {"configurable": {"thread_id": f"{thread_id_prefix}_{qid}"}}

    t0 = time.time()
    try:
        agent_out = sql_agent.invoke(state_in, config=config)
        agent_time = time.time() - t0
        pred_sql = agent_out.get("sql", "")
        pred_rows = agent_out.get("result_data", [])
        agent_error = agent_out.get("validation_error")
        attempts = agent_out.get("attempts", 1)
        intent = agent_out.get("intent", "answerable")
    except Exception as e:
        agent_time = time.time() - t0
        return {
            "question_id": qid,
            "db_id": db_id,
            "difficulty": difficulty,
            "success": False,
            "error": f"Agent crashed: {e}",
            "latency_s": agent_time,
            "execution_accuracy": False,
        }

    # 3. Compare Results
    is_accurate = False
    if gold_ok and pred_sql and not agent_error:
        # Run pred SQL through clean SQLite connection for fair comparison
        pred_ok, pred_clean_rows, _ = run_sqlite_query(db_path, pred_sql)
        if pred_ok:
            is_accurate = compare_result_sets(pred_clean_rows, gold_rows)

    if verbose:
        status_icon = "✅" if is_accurate else "❌"
        logger.info(
            "%s QID %s [%s] in %.2fs (attempts=%d) | Accurate: %s",
            status_icon,
            qid,
            difficulty,
            agent_time,
            attempts,
            is_accurate,
        )

    return {
        "question_id": qid,
        "db_id": db_id,
        "difficulty": difficulty,
        "question": question,
        "gold_sql": gold_sql,
        "pred_sql": pred_sql,
        "gold_row_count": len(gold_rows),
        "pred_row_count": len(pred_rows),
        "execution_accuracy": is_accurate,
        "attempts": attempts,
        "intent": intent,
        "agent_error": agent_error,
        "latency_s": round(agent_time, 2),
    }


def run_evaluation(
    dataset_path: Path,
    db_filter: str | None = None,
    limit: int | None = None,
    verbose: bool = True,
) -> dict[str, Any]:
    """Runs evaluation over a benchmark file and compiles comprehensive metrics."""
    logger.info("Loading benchmark from %s", dataset_path)
    data = json.loads(dataset_path.read_text(encoding="utf-8"))

    if db_filter:
        data = [q for q in data if q.get("db_id") == db_filter]
        logger.info("Filtered to %d questions for db_id=%s", len(data), db_filter)

    if limit and limit < len(data):
        data = data[:limit]
        logger.info("Limited evaluation to first %d questions", limit)

    results = []
    by_diff: dict[str, dict[str, int]] = {}

    start_time = time.time()
    for idx, sample in enumerate(data, 1):
        diff = sample.get("difficulty", "simple")
        if diff not in by_diff:
            by_diff[diff] = {"total": 0, "correct": 0}
        by_diff[diff]["total"] += 1

        res = evaluate_sample(sample, thread_id_prefix=f"eval_{int(start_time)}", verbose=verbose)
        results.append(res)

        if res.get("execution_accuracy"):
            by_diff[diff]["correct"] += 1

    total_time = time.time() - start_time
    total_q = len(results)
    total_correct = sum(1 for r in results if r.get("execution_accuracy"))
    overall_acc = (total_correct / total_q) * 100 if total_q > 0 else 0.0

    report = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "dataset_file": str(dataset_path),
        "db_filter": db_filter,
        "total_evaluated": total_q,
        "total_correct": total_correct,
        "overall_accuracy_pct": round(overall_acc, 2),
        "total_duration_s": round(total_time, 2),
        "avg_latency_s": round(total_time / total_q, 2) if total_q > 0 else 0.0,
        "by_difficulty": {
            d: {
                "total": stats["total"],
                "correct": stats["correct"],
                "accuracy_pct": round((stats["correct"] / stats["total"]) * 100, 2)
                if stats["total"] > 0
                else 0.0,
            }
            for d, stats in by_diff.items()
        },
        "results": results,
    }

    # Save Report
    reports_dir = ROOT_DIR / "eval" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_file = reports_dir / f"eval_accuracy_{int(start_time)}.json"
    report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info("Evaluation report saved to %s", report_file)

    # Print summary table
    print("\n" + "=" * 60)
    print("      EVALUATION ACCURACY BENCHMARK SUMMARY")
    print("=" * 60)
    print(f"Total Questions Evaluated: {total_q}")
    print(f"Overall Execution Accuracy: {overall_acc:.2f}% ({total_correct}/{total_q})")
    print(f"Total Duration:            {total_time:.2f}s (Avg {report['avg_latency_s']}s/query)")
    print("-" * 60)
    print(f"{'Difficulty':<15} | {'Evaluated':<10} | {'Correct':<10} | {'Accuracy':<10}")
    print("-" * 60)
    for d, stats in report["by_difficulty"].items():
        print(f"{d:<15} | {stats['total']:<10} | {stats['correct']:<10} | {stats['accuracy_pct']:.2f}%")
    print("=" * 60 + "\n")

    return report


def main():
    parser = argparse.ArgumentParser(description="Evaluate SQL Agent on BIRD benchmark questions.")
    parser.add_argument(
        "--dataset",
        type=str,
        default="./data/benchmarks/bird/dev.json",
        help="Path to benchmark questions JSON",
    )
    parser.add_argument("--db", type=str, default="financial", help="Filter by specific db_id")
    parser.add_argument("--limit", type=int, default=10, help="Number of questions to evaluate")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-question verbose logging")

    args = parser.parse_args()
    run_evaluation(
        dataset_path=Path(args.dataset),
        db_filter=args.db if args.db != "all" else None,
        limit=args.limit,
        verbose=not args.quiet,
    )


if __name__ == "__main__":
    main()
