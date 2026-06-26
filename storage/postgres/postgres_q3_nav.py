import argparse
import csv
import os
import random
import statistics
import time
from pathlib import Path

import psycopg

ROOT = Path(os.environ.get("WIKI_ROOT", "/data/wiki"))
PG_DSN = os.environ.get("PG_DSN", "postgresql://postgres:postgres@127.0.0.1:5432/wiki")

ROOT_INDEX_QUERY = """
SELECT path, content
FROM pages
WHERE path = %s
  AND type = 'file'
"""

ROOT_LS_QUERY = """
SELECT path, name, type
FROM pages
WHERE parent_path = %s
ORDER BY type, name
"""

CATEGORY_INDEX_QUERY = """
SELECT path, content
FROM pages
WHERE path = %s
  AND type = 'file'
"""

LS_QUERY = """
SELECT path, name, type
FROM pages
WHERE parent_path = %s
ORDER BY type, name
"""

GET_QUERY = """
SELECT path, name, content
FROM pages
WHERE path = %s
  AND type = 'file'
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


def fetch_all(conn, query, param):
    with conn.cursor() as cur:
        cur.execute(query, (param,))
        return cur.fetchall()


def run_nav(conn, target_path):
    wiki, chain = category_chain(target_path)
    root_path = f"{wiki}/wiki"
    start = time.perf_counter()
    steps = 0

    fetch_all(conn, ROOT_INDEX_QUERY, f"{root_path}/index.md")
    steps += 1

    fetch_all(conn, ROOT_LS_QUERY, root_path)
    steps += 1

    for category_path in chain:
        fetch_all(conn, CATEGORY_INDEX_QUERY, f"{category_path}/_index.md")
        fetch_all(conn, LS_QUERY, category_path)
        steps += 2

    rows = fetch_all(conn, GET_QUERY, target_path)
    steps += 1

    return (time.perf_counter() - start) * 1000, steps, len(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--queries", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default="/data/wiki/log/postgres_q3_nav_times.csv")
    args = parser.parse_args()

    random.seed(args.seed)
    paths = collect_leaf_pages(Path(args.root))
    sampled = random.choices(paths, k=args.queries)

    with psycopg.connect(PG_DSN) as conn:
        items = [run_nav(conn, path) for path in sampled]

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

    print("query_type=POSTGRES_Q3_NAV")
    print(f"queries={len(items)} hit={hit}")
    print(f"avg_steps={statistics.mean(steps):.3f}")
    print(f"p50_ms={statistics.median(times):.3f}")
    print(f"p95_ms={percentile(times, 95):.3f}")
    print(f"p99_ms={percentile(times, 99):.3f}")
    print(f"output={output_path}")


if __name__ == "__main__":
    main()
