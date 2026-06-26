import argparse
import csv
import json
import os
import random
import statistics
import time
from pathlib import Path

import plyvel

ROOT = Path(os.environ.get("WIKI_ROOT", "/data/wiki"))
LEVELDB_PATH = Path(os.environ.get("LEVELDB_PATH", "/data/wiki/leveldb/wiki_pages.ldb"))


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


def get_file(db, path):
    value = db.get(path.encode("utf-8"))
    return [] if value is None else [(path, value)]


def list_children(db, path):
    prefix = f"__children__:{path}/".encode("utf-8")
    rows = []
    for _, value in db.iterator(prefix=prefix):
        meta = json.loads(value.decode("utf-8"))
        rows.append((meta["path"], meta["name"], meta["type"]))
    rows.sort(key=lambda row: (row[2], row[1]))
    return rows


def run_nav(db, target_path):
    wiki, chain = category_chain(target_path)
    root_path = f"{wiki}/wiki"
    start = time.perf_counter()
    steps = 0

    get_file(db, f"{root_path}/index.md")
    steps += 1

    list_children(db, root_path)
    steps += 1

    for category_path in chain:
        get_file(db, f"{category_path}/_index.md")
        list_children(db, category_path)
        steps += 2

    rows = get_file(db, target_path)
    steps += 1

    return (time.perf_counter() - start) * 1000, steps, len(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--leveldb", default=str(LEVELDB_PATH))
    parser.add_argument("--queries", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default="/data/wiki/log/leveldb_q3_nav_times.csv")
    args = parser.parse_args()

    random.seed(args.seed)
    paths = collect_leaf_pages(Path(args.root))
    sampled = random.choices(paths, k=args.queries)

    db = plyvel.DB(args.leveldb, create_if_missing=False)
    try:
        items = [run_nav(db, path) for path in sampled]
    finally:
        db.close()

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

    print("query_type=LEVELDB_Q3_NAV")
    print(f"queries={len(items)} hit={hit}")
    print(f"avg_steps={statistics.mean(steps):.3f}")
    print(f"p50_ms={statistics.median(times):.3f}")
    print(f"p95_ms={percentile(times, 95):.3f}")
    print(f"p99_ms={percentile(times, 99):.3f}")
    print(f"output={output_path}")


if __name__ == "__main__":
    main()
