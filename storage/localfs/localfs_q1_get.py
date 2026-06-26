import argparse
import csv
import os
import random
import statistics
import time
from pathlib import Path

ROOT = Path(os.environ.get("WIKI_ROOT", "/data/wiki"))
MAX_BYTES = int(os.environ.get("LOCALFS_MAX_BYTES", str(200 * 1024)))


def percentile(values, pct):
    values = sorted(values)
    idx = int(len(values) * pct / 100)
    return values[min(idx, len(values) - 1)]


def collect_page_paths(root):
    paths = []
    for p in root.glob("*/wiki/**/*.md"):
        if "logs" in p.parts:
            continue
        rel = p.relative_to(root).as_posix()
        if p.name == "index.md" or p.parent.name != "wiki":
            paths.append(rel)
    return paths


def run_once(root, path):
    start = time.perf_counter()
    file_path = root / path
    rows = 0
    if file_path.is_file():
        file_path.read_bytes()[:MAX_BYTES]
        rows = 1
    return (time.perf_counter() - start) * 1000, rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--queries", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default="/data/wiki/log/localfs_q1_get_times.csv")
    args = parser.parse_args()

    root = Path(args.root)
    random.seed(args.seed)
    paths = collect_page_paths(root)
    sampled = random.choices(paths, k=args.queries)

    items = [run_once(root, path) for path in sampled]
    times = [x[0] for x in items]
    hit = sum(1 for _, rows in items if rows > 0)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["idx", "path", "elapsed_ms", "rows"])
        for idx, (path, (elapsed_ms, rows)) in enumerate(zip(sampled, items), 1):
            writer.writerow([idx, path, f"{elapsed_ms:.6f}", rows])

    print("query_type=LOCALFS_Q1_GET")
    print(f"queries={len(items)} hit={hit}")
    print(f"p50_ms={statistics.median(times):.3f}")
    print(f"p95_ms={percentile(times, 95):.3f}")
    print(f"p99_ms={percentile(times, 99):.3f}")
    print(f"output={output_path}")


if __name__ == "__main__":
    main()
