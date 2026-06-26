import json
import os
import re
from pathlib import Path

import psycopg

ROOT = Path(os.environ.get("WIKI_ROOT", "/data/wiki"))
BIZUIN_PATH = Path(os.environ.get("BIZUIN_PATH", ROOT / "bizuin.json"))
PG_DSN = os.environ.get("PG_DSN", "postgresql://postgres:postgres@127.0.0.1:5432/wiki")
MAX_BYTES = int(os.environ.get("POSTGRES_MAX_BYTES", str(200 * 1024)))
PROGRESS_EVERY = int(os.environ.get("POSTGRES_PROGRESS_EVERY", "100"))
SKIP_DIRS = {"logs", "log", "__pycache__"}


def load_bizuin() -> dict[str, str]:
    data = json.loads(BIZUIN_PATH.read_text(encoding="utf-8"))
    return {k: str(v["uin"]) for k, v in data.items()}


def read_text(path: Path) -> str:
    try:
        return path.read_bytes()[:MAX_BYTES].decode("utf-8", errors="ignore")
    except Exception:
        return ""


def to_ltree(path: str) -> str:
    labels = []
    for part in Path(path).parts:
        label = re.sub(r"[^0-9A-Za-z_]+", "_", part).strip("_")
        if not label:
            label = "x"
        if label[0].isdigit():
            label = "x_" + label
        labels.append(label[:255])
    return ".".join(labels)


def metadata_from_text(text: str) -> dict:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}
    meta = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip('"')
    return meta


def iter_nodes(wiki_key: str, bizuin: str):
    wiki_root = ROOT / f"{wiki_key}_wiki" / "wiki"
    if not wiki_root.exists():
        print(f"skip {wiki_key}: missing {wiki_root}", flush=True)
        return

    for entry in sorted(wiki_root.rglob("*")):
        if any(part in SKIP_DIRS for part in entry.parts):
            continue

        rel = entry.relative_to(wiki_root).as_posix()
        path = entry.relative_to(ROOT).as_posix()
        parent_path = entry.parent.relative_to(ROOT).as_posix() if entry.parent != wiki_root else f"{wiki_key}_wiki/wiki"
        stat = entry.stat()

        if entry.is_dir():
            yield {
                "wiki_key": wiki_key,
                "bizuin": bizuin,
                "path": path,
                "ltree_path": to_ltree(path),
                "parent_path": parent_path,
                "name": entry.name,
                "type": "dir",
                "content": "",
                "metadata": {},
                "size": 0,
                "mtime": stat.st_mtime,
            }
        elif entry.is_file() and entry.suffix.lower() == ".md":
            text = read_text(entry)
            yield {
                "wiki_key": wiki_key,
                "bizuin": bizuin,
                "path": path,
                "ltree_path": to_ltree(path),
                "parent_path": parent_path,
                "name": entry.name,
                "type": "file",
                "content": text,
                "metadata": metadata_from_text(text),
                "size": stat.st_size,
                "mtime": stat.st_mtime,
            }


def upsert_page(cur, row: dict) -> None:
    cur.execute(
        """
        INSERT INTO pages (
            wiki_key, bizuin, path, ltree_path, parent_path, name, type,
            content, metadata, size, mtime
        )
        VALUES (
            %(wiki_key)s, %(bizuin)s, %(path)s, %(ltree_path)s::ltree,
            %(parent_path)s, %(name)s, %(type)s, %(content)s,
            %(metadata)s::jsonb, %(size)s, to_timestamp(%(mtime)s)
        )
        ON CONFLICT (path) DO UPDATE SET
            wiki_key = EXCLUDED.wiki_key,
            bizuin = EXCLUDED.bizuin,
            ltree_path = EXCLUDED.ltree_path,
            parent_path = EXCLUDED.parent_path,
            name = EXCLUDED.name,
            type = EXCLUDED.type,
            content = EXCLUDED.content,
            metadata = EXCLUDED.metadata,
            size = EXCLUDED.size,
            mtime = EXCLUDED.mtime
        """,
        {**row, "metadata": json.dumps(row["metadata"], ensure_ascii=False)},
    )


def main():
    bizuins = load_bizuin()
    total = 0

    with psycopg.connect(PG_DSN) as conn:
        with conn.cursor() as cur:
            for wiki_key, bizuin in sorted(bizuins.items()):
                wiki_total = 0
                for row in iter_nodes(wiki_key, bizuin):
                    upsert_page(cur, row)
                    total += 1
                    wiki_total += 1
                    if PROGRESS_EVERY > 0 and total % PROGRESS_EVERY == 0:
                        conn.commit()
                        print(f"progress total={total}", flush=True)
                conn.commit()
                print(f"wiki={wiki_key} rows={wiki_total}", flush=True)

    print(f"all rows={total}", flush=True)


if __name__ == "__main__":
    main()
