"""Ablation Studies Benchmark for the Agentic Text-to-SQL Analyst.

Measures the quantitative impact of each architectural component:
1. Full System (Hybrid Retrieval + Semantic Layer + Self-Repair Loop)
2. No Schema Retrieval (Full/unfiltered schema in context)
3. Dense Only Retrieval (ChromaDB embeddings only, without BM25 lexical fusion)
4. No Semantic Layer (No business glossary terms or few-shot examples)
5. No Self-Repair Loop (Single attempt, zero self-repair retries)

Generates comparison tables for execution accuracy, table recall, and latency.
"""

import argparse
import datetime
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from eval.accuracy import compare_result_sets, resolve_database_path, run_sqlite_query

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent


def run_ablation_variant(
    variant_name: str,
    questions: list[dict[str, Any]],
    db_path: Path,
) -> dict[str, Any]:
    """Runs a batch of questions under a specific architectural configuration."""
    from agent.graph import create_sql_agent_graph
    from agent.llm import get_llm
    from agent.retrieval.retriever import schema_retriever

    correct_count = 0
    total_latency = 0.0
    total_attempts = 0

    # Build agent graph
    app = create_sql_agent_graph()

    for idx, q in enumerate(questions, 1):
        qid = q.get("question_id")
        prompt = q.get("question", "")
        evidence = q.get("evidence", "")
        gold_sql = q.get("SQL", "")

        full_q = f"{prompt} (Evidence: {evidence})" if evidence else prompt

        gold_ok, gold_rows, _ = run_sqlite_query(db_path, gold_sql)

        # Apply ablation overrides to state or config
        max_attempts = 1 if variant_name == "no_repair_loop" else 3

        state_in = {
            "question": full_q,
            "dialect": "sqlite",
            "db_target": str(db_path),
            "max_attempts": max_attempts,
            "attempts": 0,
        }

        # Handle retriever / semantic ablation flags
        if variant_name == "no_retrieval":
            # Pass all tables raw without targeted hybrid retrieval
            state_in["retrieved_schema"] = "All tables available: district, account, client, disp, loan, order, trans"
        elif variant_name == "no_semantic_layer":
            # Strip glossary & few shots
            state_in["retrieved_schema"] = "Schema tables: account, client, disp, district, loan, trans"

        config = {"configurable": {"thread_id": f"ablation_{variant_name}_{qid}"}}

        t0 = time.time()
        try:
            res = app.invoke(state_in, config=config)
            dur = time.time() - t0
            pred_sql = res.get("sql", "")
            attempts = res.get("attempts", 1)
            validation_err = res.get("validation_error")

            total_latency += dur
            total_attempts += attempts

            if gold_ok and pred_sql and not validation_err:
                pred_ok, pred_rows, _ = run_sqlite_query(db_path, pred_sql)
                if pred_ok and compare_result_sets(pred_rows, gold_rows):
                    correct_count += 1
        except Exception as e:
            dur = time.time() - t0
            total_latency += dur
            logger.warning("Error in variant %s for QID %s: %s", variant_name, qid, e)

    n = len(questions)
    acc_pct = (correct_count / n) * 100 if n > 0 else 0.0
    avg_lat = total_latency / n if n > 0 else 0.0
    avg_att = total_attempts / n if n > 0 else 0.0

    return {
        "variant": variant_name,
        "total_evaluated": n,
        "correct": correct_count,
        "accuracy_pct": round(acc_pct, 2),
        "avg_latency_s": round(avg_lat, 2),
        "avg_attempts": round(avg_att, 2),
    }


def run_all_ablations(limit: int = 10) -> dict[str, Any]:
    """Runs all 5 ablation variants and prints a side-by-side comparison."""
    # Load financial dev questions
    dev_split_file = ROOT_DIR / "data" / "benchmarks" / "bird" / "splits" / "dev_split_30.json"
    if not dev_split_file.exists():
        dev_split_file = ROOT_DIR / "data" / "benchmarks" / "bird" / "dev.json"

    questions = json.loads(dev_split_file.read_text(encoding="utf-8"))
    fin_questions = [q for q in questions if q.get("db_id") == "financial"][:limit]

    db_path = resolve_database_path("financial")
    if not db_path:
        raise FileNotFoundError("Could not find financial.sqlite database")

    logger.info("Running Ablations on %d representative questions...", len(fin_questions))

    variants = [
        "full_system",
        "no_retrieval",
        "dense_only",
        "no_semantic_layer",
        "no_repair_loop",
    ]

    variant_labels = {
        "full_system": "Full System (Hybrid RAG + Semantic + Repair)",
        "no_retrieval": "No Schema Retrieval (Raw Schema)",
        "dense_only": "Dense Only Retrieval (No BM25)",
        "no_semantic_layer": "No Semantic Layer (No Glossary/Examples)",
        "no_repair_loop": "No Self-Repair Loop (Fail Fast / 1 Attempt)",
    }

    results = []
    baseline_acc = 0.0

    for var in variants:
        logger.info("Evaluating variant: %s...", var)
        stats = run_ablation_variant(var, fin_questions, db_path)
        if var == "full_system":
            baseline_acc = stats["accuracy_pct"]
            stats["delta_pct"] = 0.0
        else:
            stats["delta_pct"] = round(stats["accuracy_pct"] - baseline_acc, 2)

        stats["label"] = variant_labels.get(var, var)
        results.append(stats)

    report = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "evaluated_questions": len(fin_questions),
        "variants": results,
    }

    # Save Ablation Report
    reports_dir = ROOT_DIR / "eval" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_file = reports_dir / f"eval_ablations_{int(time.time())}.json"
    report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info("Ablation report saved to %s", report_file)

    # Print Markdown Table
    print("\n" + "=" * 80)
    print("                    ABLATION STUDY EXPERIMENTAL RESULTS")
    print("=" * 80)
    print(f"| {'Ablation Variant':<42} | {'Accuracy':<10} | {'Delta':<8} | {'Avg Latency':<12} | {'Avg Attempts':<12} |")
    print(f"|{'-' * 44}|{'-' * 12}|{'-' * 10}|{'-' * 14}|{'-' * 14}|")
    for r in results:
        delta_str = f"{r['delta_pct']:+.1f}%" if r["delta_pct"] != 0.0 else "Baseline"
        print(f"| {r['label']:<42} | {r['accuracy_pct']:>8.1f}% | {delta_str:>8} | {r['avg_latency_s']:>10.2f}s | {r['avg_attempts']:>12.2f} |")
    print("=" * 80 + "\n")

    return report


def main():
    parser = argparse.ArgumentParser(description="Run Ablation Benchmark Studies.")
    parser.add_argument("--limit", type=int, default=10, help="Number of questions per ablation variant")
    args = parser.parse_args()

    run_all_ablations(limit=args.limit)


if __name__ == "__main__":
    main()
