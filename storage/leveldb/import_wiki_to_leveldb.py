import json
import os
import shutil
from pathlib import Path

import plyvel

ROOT = Path(os.environ.get("WIKI_ROOT", "/data/wiki"))
BIZUIN_PATH = Path(os.environ.get("BIZUIN_PATH", ROOT / "bizuin.json"))
LEVELDB_PATH = Path(os.environ.get("LEVELDB_PATH", "/data/wiki/leveldb/wiki_pages.ldb"))
MAX_BYTES = int(os.environ.get("LEVELDB_MAX_BYTES", str(200 * 1024)))
PROGRESS_EVERY = int(os.environ.get("LEVELDB_PROGRESS_EVERY", "100"))
RESET = os.environ.get("LEVELDB_RESET", "1") == "1"
SKIP_DIRS = {"logs", "log", "__pycache__"}


def load_bizuin() -> dict[str, str]:
    data = json.loads(BIZUIN_PATH.read_text(encoding="utf-8"))
    return {k: str(v["uin"]) for k, v in data.items()}


def read_text(path: Path) -> str:
    try:
        return path.read_bytes()[:MAX_BYTES].decode("utf-8", errors="ignore")
    except Exception:
        return ""


def iter_nodes(wiki_key: str, bizuin: str):
    wiki_root = ROOT / f"{wiki_key}_wiki" / "wiki"
    if not wiki_root.exists():
        print(f"skip {wiki_key}: missing {wiki_root}", flush=True)
        return

    for entry in sorted(wiki_root.rglob("*")):
        if any(part in SKIP_DIRS for part in entry.parts):
            continue

        path = entry.relative_to(ROOT).as_posix()
        parent_path = entry.parent.relative_to(ROOT).as_posix() if entry.parent != wiki_root else f"{wiki_key}_wiki/wiki"
        stat = entry.stat()

        if entry.is_dir():
            yield {
                "wiki_key": wiki_key,
                "bizuin": bizuin,
                "path": path,
                "parent_path": parent_path,
                "name": entry.name,
                "type": "dir",
                "content": "",
                "size": 0,
                "mtime": stat.st_mtime,
            }
        elif entry.is_file() and entry.suffix.lower() == ".md":
            yield {
                "wiki_key": wiki_key,
                "bizuin": bizuin,
                "path": path,
                "parent_path": parent_path,
                "name": entry.name,
                "type": "file",
                "content": read_text(entry),
                "size": stat.st_size,
                "mtime": stat.st_mtime,
            }


def main():
    if RESET and LEVELDB_PATH.exists():
        shutil.rmtree(LEVELDB_PATH)
    LEVELDB_PATH.parent.mkdir(parents=True, exist_ok=True)

    bizuins = load_bizuin()
    total = 0

    db = plyvel.DB(str(LEVELDB_PATH), create_if_missing=True)
    try:
        with db.write_batch() as batch:
            for wiki_key, bizuin in sorted(bizuins.items()):
                wiki_total = 0
                for row in iter_nodes(wiki_key, bizuin):
                    key = row["path"].encode("utf-8")
                    meta_key = f"__meta__:{row['path']}".encode("utf-8")
                    child_key = f"__children__:{row['parent_path']}/{row['name']}".encode("utf-8")
                    meta_value = json.dumps({
                        "wiki_key": row["wiki_key"],
                        "bizuin": row["bizuin"],
                        "path": row["path"],
                        "parent_path": row["parent_path"],
                        "name": row["name"],
                        "type": row["type"],
                        "size": row["size"],
                        "mtime": row["mtime"],
                    }, ensure_ascii=False).encode("utf-8")
                    if row["type"] == "file":
                        batch.put(key, row["content"].encode("utf-8"))
                    batch.put(meta_key, meta_value)
                    batch.put(child_key, meta_value)

                    total += 1
                    wiki_total += 1
                    if PROGRESS_EVERY > 0 and total % PROGRESS_EVERY == 0:
                        print(f"progress total={total}", flush=True)
                print(f"wiki={wiki_key} rows={wiki_total}", flush=True)
    finally:
        db.close()

    print(f"all rows={total}", flush=True)
    print(f"leveldb={LEVELDB_PATH}", flush=True)


if __name__ == "__main__":
    main()
