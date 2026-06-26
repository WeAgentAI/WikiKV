import argparse
import csv
import os
import random
import statistics
import time
from pathlib import Path

from neo4j import GraphDatabase

ROOT = Path(os.environ.get("WIKI_ROOT", "/data/wiki"))
URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
USER = os.environ.get("NEO4J_USER", "neo4j")
PWD = os.environ.get("NEO4J_PWD", "12345678")

QUERY = """
MATCH (c:Category {path:$path})
OPTIONAL MATCH (c)-[:HAS_CHILD]->(sub:Category)
OPTIONAL MATCH (c)-[:CONTAINS]->(p:Page)
RETURN collect(DISTINCT sub.path) AS subdirs,
       collect(DISTINCT p.path) AS pages
"""


def percentile(values, pct):
    values = sorted(values)
    idx = int(len(values) * pct / 100)
    return values[min(idx, len(values) - 1)]


def collect_category_paths(root):
    paths = []
    for p in root.glob("*/wiki/**"):
        if p.is_dir() and p.name != "wiki" and "logs" not in p.parts:
            paths.append(p.relative_to(root).as_posix())
    return paths


def run_once(session, path):
    start = time.perf_counter()
    rows = list(session.run(QUERY, path=path))
    elapsed = (time.perf_counter() - start) * 1000
    total = 0
    if rows:
        total = len(rows[0]["subdirs"]) + len(rows[0]["pages"])
    return elapsed, total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--queries", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default="/data/wiki/log/neo4j_q2_ls_times.csv")
    args = parser.parse_args()

    random.seed(args.seed)
    paths = collect_category_paths(Path(args.root))
    sampled = random.choices(paths, k=args.queries)

    driver = GraphDatabase.driver(URI, auth=(USER, PWD))
    try:
        with driver.session() as session:
            items = [run_once(session, path) for path in sampled]
    finally:
        driver.close()

    times = [x[0] for x in items]
    nonempty = sum(1 for _, total in items if total > 0)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["idx", "path", "elapsed_ms", "result_count"])
        for idx, (path, (elapsed_ms, total)) in enumerate(zip(sampled, items), 1):
            writer.writerow([idx, path, f"{elapsed_ms:.6f}", total])

    print(f"query_type=Q2_LS")
    print(f"queries={len(items)} nonempty={nonempty}")
    print(f"p50_ms={statistics.median(times):.3f}")
    print(f"p95_ms={percentile(times, 95):.3f}")
    print(f"p99_ms={percentile(times, 99):.3f}")
    print(f"output={output_path}")


if __name__ == "__main__":
    main()
