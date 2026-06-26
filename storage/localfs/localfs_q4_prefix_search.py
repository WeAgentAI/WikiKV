import argparse
import csv
import os
import random
import statistics
import time
from pathlib import Path

ROOT = Path(os.environ.get("WIKI_ROOT", "/data/wiki"))
SKIP_DIRS = {"logs", "log", "__pycache__"}


def percentile(values, pct):
    values = sorted(values)
    idx = int(len(values) * pct / 100)
    return values[min(idx, len(values) - 1)]


def collect_prefixes(root):
    prefixes = set()
    for p in root.glob("*/wiki/**"):
        if p.is_dir() and not any(part in SKIP_DIRS for part in p.parts):
            prefixes.add(p.relative_to(root).as_posix() + "/")
    return sorted(prefixes)


def iter_md_files(prefix_path):
    for dirpath, dirnames, filenames in os.walk(prefix_path):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name.lower().endswith(".md"):
                yield Path(dirpath) / name


def run_once(root, prefix):
    start = time.perf_counter()
    rows = 0
    prefix_path = root / prefix
    if prefix_path.is_dir():
        for _ in iter_md_files(prefix_path):
            rows += 1
    return (time.perf_counter() - start) * 1000, rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--queries", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default="/data/wiki/log/localfs_q4_prefix_search_times.csv")
    args = parser.parse_args()

    root = Path(args.root)
    random.seed(args.seed)
    prefixes = collect_prefixes(root)
    sampled = random.choices(prefixes, k=args.queries)

    items = [run_once(root, prefix) for prefix in sampled]
    times = [x[0] for x in items]
    nonempty = sum(1 for _, rows in items if rows > 0)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["idx", "prefix", "elapsed_ms", "rows"])
        for idx, (prefix, (elapsed_ms, rows)) in enumerate(zip(sampled, items), 1):
            writer.writerow([idx, prefix, f"{elapsed_ms:.6f}", rows])

    print("query_type=LOCALFS_Q4_PREFIX_SEARCH")
    print(f"queries={len(items)} nonempty={nonempty}")
    print(f"p50_ms={statistics.median(times):.3f}")
    print(f"p95_ms={percentile(times, 95):.3f}")
    print(f"p99_ms={percentile(times, 99):.3f}")
    print(f"output={output_path}")


if __name__ == "__main__":
    main()
