"""Phase 4 — 추출 요구사항 → 벡터DB 적재.

_extracted/*.json 의 각 요구사항(row) 1건을 1 청크로 임베딩하여
ChromaDB 컬렉션에 doc_type=requirement 메타데이터와 함께 적재한다.

청크 본문(임베딩 대상)은 검색 적중률을 위해
  "요구사항명 — 요구사항 상세 (유형) [대응전략]"
형태로 합성한다.

환경: 임베딩 provider 설정 필요 (OpenAI: OPENAI_API_KEY / local: sentence-transformers)

Usage:
  .venv/bin/python scripts/requirements/ingest_requirements.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
EXTRACTED_DIR = ROOT / "docs" / "requirements" / "_extracted"

import yaml  # noqa: E402

SLUGS = yaml.safe_load((ROOT / "docs" / "projects" / "_slugs.yaml").read_text(encoding="utf-8"))


def load_env() -> None:
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def year_of(slug: str, rel: str) -> str:
    import re
    m = re.search(r"(19|20)\d{2}", slug) or re.search(r"(19|20)\d{2}", rel)
    return m.group(0) if m else ""


def build_chunks() -> list[dict]:
    chunks: list[dict] = []
    for f in sorted(EXTRACTED_DIR.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        slug = d["project_slug"]
        for i, r in enumerate(d["requirements"], 1):
            req_id = f"{slug}#R-{i:03d}__{f.stem}"
            name = r.get("req_name", "")
            detail = r.get("req_detail", "")
            rtype = r.get("req_type", "기타")
            strat = r.get("strategy", "")
            loc = r.get("source_loc", "")
            text = f"[{d['project_title']}] {name} — {detail} (유형:{rtype})"
            if strat and strat != "(원문 미기재)":
                text += f" [대응전략: {strat}]"
            chunks.append({
                "id": req_id,
                "text": text,
                "metadata": {
                    "req_name": name,
                    "req_type": rtype,
                    "strategy": strat,
                    "project": slug,
                    "project_title": d["project_title"],
                    "domain": d.get("domain", "etc"),
                    "year": year_of(slug, d["source_rel"]),
                    "source": d["source_file"] + (f" #{loc}" if loc else ""),
                    "source_rel": d["source_rel"],
                    "doc_type": "requirement",
                },
            })
    return chunks


async def main() -> int:
    load_env()
    chunks = build_chunks()
    if not chunks:
        print("[WARN] _extracted/ 비어있음 — 먼저 extract_requirements.py 실행 필요")
        return 1
    print(f"적재 대상 요구사항 청크: {len(chunks)}건")

    from app.embedding.embedder import DocumentEmbedder
    from app.vectordb.store import VectorStore

    embedder = DocumentEmbedder()
    store = VectorStore()

    texts = [c["text"] for c in chunks]
    print(f"임베딩 생성 중 (provider={embedder._provider}, model={embedder.model})...")
    vectors = await embedder.embed_batch(texts)

    store.upsert_batch(
        ids=[c["id"] for c in chunks],
        embeddings=vectors,
        metadatas=[c["metadata"] for c in chunks],
        documents=texts,
    )
    print(f"[DONE] {len(chunks)}건 적재 완료 → 컬렉션 '{store.COLLECTION_NAME}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
