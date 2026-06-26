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

ROOT_INDEX_QUERY = """
MATCH (w:Wiki {name:$wiki})-[:HAS_PAGE]->(idx:Page {name:'index.md'})
RETURN idx.path AS path, idx.content AS content
"""

ROOT_LS_QUERY = """
MATCH (w:Wiki {name:$wiki})
OPTIONAL MATCH (w)-[:HAS_CATEGORY]->(c:Category)
OPTIONAL MATCH (w)-[:HAS_PAGE]->(p:Page)
RETURN collect(DISTINCT c.path) AS categories,
       collect(DISTINCT p.path) AS pages
"""

CATEGORY_INDEX_QUERY = """
MATCH (c:Category {path:$path})-[:CONTAINS]->(idx:Page {name:'_index.md'})
RETURN idx.path AS path, idx.content AS content
"""

LS_QUERY = """
MATCH (c:Category {path:$path})
OPTIONAL MATCH (c)-[:HAS_CHILD]->(sub:Category)
OPTIONAL MATCH (c)-[:CONTAINS]->(p:Page)
RETURN collect(DISTINCT sub.path) AS subdirs,
       collect(DISTINCT p.path) AS pages
"""

GET_QUERY = """
MATCH (p:Page {path:$path})
RETURN p.path AS path, p.name AS name, p.content AS content
"""


def percentile(values, pct):
    values = sorted(values)
    idx = int(len(values) * pct / 100)
    return values[min(idx, len(values) - 1)]


def collect_leaf_pages(root):
    pages = []
    for p in root.glob("*/wiki/**/*.md"):
        if "logs" in p.parts or p.name in {"index.md", "_index.md"}:
            continue
        pages.append(p.relative_to(root).as_posix())
    return pages


def category_chain(page_path):
    parts = page_path.split("/")
    wiki = parts[0]
    dirs = parts[2:-1]
    chain = []
    cur = f"{wiki}/wiki"
    for d in dirs:
        cur = f"{cur}/{d}"
        chain.append(cur)
    return wiki, chain


def run_nav(session, target_path):
    wiki, chain = category_chain(target_path)
    start = time.perf_counter()
    steps = 0

    list(session.run(ROOT_INDEX_QUERY, wiki=wiki))
    steps += 1

    list(session.run(ROOT_LS_QUERY, wiki=wiki))
    steps += 1

    for category_path in chain:
        list(session.run(CATEGORY_INDEX_QUERY, path=category_path))
        list(session.run(LS_QUERY, path=category_path))
        steps += 2

    rows = list(session.run(GET_QUERY, path=target_path))
    steps += 1

    return (time.perf_counter() - start) * 1000, steps, len(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--queries", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default="/data/wiki/log/neo4j_q3_nav_times.csv")
    args = parser.parse_args()

    random.seed(args.seed)
    paths = collect_leaf_pages(Path(args.root))
    sampled = random.choices(paths, k=args.queries)

    driver = GraphDatabase.driver(URI, auth=(USER, PWD))
    try:
        with driver.session() as session:
            items = [run_nav(session, path) for path in sampled]
    finally:
        driver.close()

    times = [x[0] for x in items]
    steps = [x[1] for x in items]
    hit = sum(1 for _, _, rows in items if rows > 0)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["idx", "target_path", "elapsed_ms", "steps", "rows"])
        for idx, (path, (elapsed_ms, step_count, rows)) in enumerate(zip(sampled, items), 1):
            writer.writerow([idx, path, f"{elapsed_ms:.6f}", step_count, rows])

    print(f"query_type=Q3_NAV")
    print(f"queries={len(items)} hit={hit}")
    print(f"avg_steps={statistics.mean(steps):.3f}")
    print(f"p50_ms={statistics.median(times):.3f}")
    print(f"p95_ms={percentile(times, 95):.3f}")
    print(f"p99_ms={percentile(times, 99):.3f}")
    print(f"output={output_path}")


if __name__ == "__main__":
    main()
