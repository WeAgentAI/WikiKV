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

QUERY = """
SELECT path, name
FROM pages
WHERE type = 'file'
  AND path LIKE %s
ORDER BY path
"""


def percentile(values, pct):
    values = sorted(values)
    idx = int(len(values) * pct / 100)
    return values[min(idx, len(values) - 1)]


def collect_prefixes(root):
    prefixes = set()
    for p in root.glob("*/wiki/**"):
        if p.is_dir() and "logs" not in p.parts:
            rel = p.relative_to(root).as_posix()
            prefixes.add(rel + "/")
    return sorted(prefixes)


def run_once(conn, prefix):
    start = time.perf_counter()
    with conn.cursor() as cur:
        cur.execute(QUERY, (prefix + "%",))
        rows = cur.fetchall()
    return (time.perf_counter() - start) * 1000, len(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--queries", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default="/data/wiki/log/postgres_q4_prefix_search_times.csv")
    args = parser.parse_args()

    random.seed(args.seed)
    prefixes = collect_prefixes(Path(args.root))
    sampled = random.choices(prefixes, k=args.queries)

    with psycopg.connect(PG_DSN) as conn:
        items = [run_once(conn, prefix) for prefix in sampled]

    times = [x[0] for x in items]
    nonempty = sum(1 for _, rows in items if rows > 0)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["idx", "prefix", "elapsed_ms", "rows"])
        for idx, (prefix, (elapsed_ms, rows)) in enumerate(zip(sampled, items), 1):
            writer.writerow([idx, prefix, f"{elapsed_ms:.6f}", rows])

    print("query_type=POSTGRES_Q4_PREFIX_SEARCH")
    print(f"queries={len(items)} nonempty={nonempty}")
    print(f"p50_ms={statistics.median(times):.3f}")
    print(f"p95_ms={percentile(times, 95):.3f}")
    print(f"p99_ms={percentile(times, 99):.3f}")
    print(f"output={output_path}")


if __name__ == "__main__":
    main()
