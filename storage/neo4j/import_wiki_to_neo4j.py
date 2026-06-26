import os
from pathlib import Path
from neo4j import GraphDatabase

ROOT = Path(os.environ.get("WIKI_ROOT", "/data/wiki"))
URI  = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
USER = os.environ.get("NEO4J_USER", "neo4j")
PWD  = os.environ.get("NEO4J_PWD",  "12345678")

SKIP_DIRS = {"logs"}
MAX_BYTES = 200 * 1024

def read_text(p: Path) -> str:
    try:
        data = p.read_bytes()[:MAX_BYTES]
        return data.decode("utf-8", errors="ignore")
    except Exception:
        return ""

def collect():
    pages, categories, wikis = [], [], []
    for wiki_dir in sorted(ROOT.iterdir()):
        if not wiki_dir.is_dir(): continue
        wiki_name = wiki_dir.name
        wikis.append({"name": wiki_name, "path": str(wiki_dir.relative_to(ROOT))})

        wiki_root = wiki_dir / "wiki"
        if not wiki_root.exists(): continue

        for entry in wiki_root.rglob("*"):
            rel = entry.relative_to(ROOT).as_posix()
            if any(part in SKIP_DIRS for part in entry.parts): continue

            if entry.is_dir():
                parts = entry.relative_to(wiki_root).parts
                if not parts: continue
                categories.append({
                    "wiki": wiki_name,
                    "path": rel,
                    "name": entry.name,
                    "depth": len(parts),
                    "parent_path": entry.parent.relative_to(ROOT).as_posix()
                                   if entry.parent != wiki_root else None,
                })
            elif entry.is_file():
                category_path = entry.parent.relative_to(ROOT).as_posix() if entry.parent != wiki_root else None
                is_index = entry.parent == wiki_root and entry.name == "index.md"
                if entry.suffix.lower() == ".md" and (category_path or is_index):
                    pages.append({
                        "wiki": wiki_name,
                        "path": rel,
                        "name": entry.name,
                        "ext": entry.suffix.lower(),
                        "size": entry.stat().st_size,
                        "content": read_text(entry),
                        "category_path": category_path,
                    })
    return wikis, categories, pages

def load(driver):
    wikis, categories, pages = collect()
    with driver.session() as s:
        s.run("CREATE CONSTRAINT wiki_name IF NOT EXISTS FOR (w:Wiki) REQUIRE w.name IS UNIQUE")
        s.run("CREATE CONSTRAINT cat_path  IF NOT EXISTS FOR (c:Category) REQUIRE c.path IS UNIQUE")
        s.run("CREATE CONSTRAINT page_path IF NOT EXISTS FOR (p:Page) REQUIRE p.path IS UNIQUE")
        s.run("CREATE INDEX page_path_prefix IF NOT EXISTS FOR (p:Page) ON (p.path)")

        s.run("UNWIND $rows AS r MERGE (w:Wiki {name:r.name}) SET w.path=r.path", rows=wikis)

        s.run("""
            OPTIONAL MATCH (:Wiki)-[rel:HAS_CATEGORY]->(c:Category)
            WHERE c.depth > 1
            DELETE rel
            WITH 1 AS _
            UNWIND $rows AS r
            MERGE (c:Category {path:r.path})
            SET c.name=r.name, c.depth=r.depth, c.wiki=r.wiki
            WITH c, r WHERE r.parent_path IS NULL
            MATCH (w:Wiki {name:r.wiki})
            MERGE (w)-[:HAS_CATEGORY]->(c)
        """, rows=categories)

        s.run("""
            UNWIND $rows AS r
            WITH r WHERE r.parent_path IS NOT NULL
            MATCH (parent:Category {path:r.parent_path}), (child:Category {path:r.path})
            MERGE (parent)-[:HAS_CHILD]->(child)
        """, rows=categories)

        s.run("""
            UNWIND $rows AS r
            MERGE (p:Page {path:r.path})
            SET p.name=r.name, p.ext=r.ext, p.size=r.size,
                p.wiki=r.wiki, p.content=r.content
            WITH p, r
            OPTIONAL MATCH (c:Category {path:r.category_path})
            FOREACH (_ IN CASE WHEN c IS NULL THEN [] ELSE [1] END |
                MERGE (c)-[:CONTAINS]->(p)
            )
            WITH p, r, c
            MATCH (w:Wiki {name:r.wiki})
            FOREACH (_ IN CASE WHEN c IS NULL THEN [1] ELSE [] END |
                MERGE (w)-[:HAS_PAGE]->(p)
            )
        """, rows=pages)

        print(f"wikis={len(wikis)} categories={len(categories)} pages={len(pages)}")

if __name__ == "__main__":
    driver = GraphDatabase.driver(URI, auth=(USER, PWD))
    try:
        load(driver)
    finally:
        driver.close()