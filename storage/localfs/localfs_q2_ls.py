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


def collect_category_paths(root):
    paths = []
    for p in root.glob("*/wiki/**"):
        if p.is_dir() and p.name != "wiki" and not any(part in SKIP_DIRS for part in p.parts):
            paths.append(p.relative_to(root).as_posix())
    return paths


def list_children(root, path):
    dir_path = root / path
    if not dir_path.is_dir():
        return []

    return [name for name in os.listdir(dir_path) if name not in SKIP_DIRS]


def run_once(root, path):
    start = time.perf_counter()
    rows = list_children(root, path)
    return (time.perf_counter() - start) * 1000, len(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--queries", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default="/data/wiki/log/localfs_q2_ls_times.csv")
    args = parser.parse_args()

    root = Path(args.root)
    random.seed(args.seed)
    paths = collect_category_paths(root)
    sampled = random.choices(paths, k=args.queries)

    items = [run_once(root, path) for path in sampled]
    times = [x[0] for x in items]
    nonempty = sum(1 for _, total in items if total > 0)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["idx", "path", "elapsed_ms", "result_count"])
        for idx, (path, (elapsed_ms, total)) in enumerate(zip(sampled, items), 1):
            writer.writerow([idx, path, f"{elapsed_ms:.6f}", total])

    print("query_type=LOCALFS_Q2_LS")
    print(f"queries={len(items)} nonempty={nonempty}")
    print(f"p50_ms={statistics.median(times):.3f}")
    print(f"p95_ms={percentile(times, 95):.3f}")
    print(f"p99_ms={percentile(times, 99):.3f}")
    print(f"output={output_path}")


if __name__ == "__main__":
    main()
