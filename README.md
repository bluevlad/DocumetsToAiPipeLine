# DocumetsToAiPipeLine

26년간(1999-2025) 축적된 IT 프로젝트 문서(약 65,000개)를 RAG(Retrieval-Augmented Generation) DB로 구축하여, 과거 아이디어의 MSP 서비스 전환 가능성을 분석하는 파이프라인.

## Architecture

```
${DOCUMENTS_ROOT}  →  [Ingestion]  →  [Chunking]  →  [Embedding]  →  [VectorDB]  →  [RAG Query]
  (65K+ documents)    HWP/DOC/PPT      Semantic       OpenAI          ChromaDB       Claude API
                      PDF/XLS/TXT      Splitting      3-large         /pgvector
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12 / FastAPI |
| Vector DB (dev) | ChromaDB |
| Vector DB (prod) | PostgreSQL + pgvector |
| Embedding | OpenAI text-embedding-3-large |
| LLM | Anthropic Claude |
| Container | Docker Compose |

## Quick Start

```bash
# 1. Install
python -m venv venv && source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. Configure (문서 소스 경로, API 키 등)
cp .env.example .env.local

# 3. Run
uvicorn app.main:app --reload --port 9060
```

## Project Structure

```
app/
├── core/           # 핵심 설정
├── ingestion/      # 문서 수집 (HWP/Office/PDF 변환)
├── embedding/      # 벡터 임베딩
├── vectordb/       # 벡터DB 저장/검색
├── rag/            # RAG 질의 엔진
└── api/v1/         # REST API
```

## Documentation

- [개발 환경 설정](docs/dev/SETUP.md)
- [임베딩/LLM 옵션 비교](docs/dev/EMBEDDING_AND_LLM_OPTIONS.md)
- [ADR: 아키텍처 결정](docs/adr/)
- [API 변경 이력](docs/api/CHANGELOG.md)
- [초기 로드맵](docs/roadmap/RAG_PIPELINE_ROADMAP.md)

> 분석 대상 문서·프로젝트별 산출물은 개인 자료를 포함하므로 별도 private 저장소에서 관리합니다.
