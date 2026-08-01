# 001. RAG 파이프라인 아키텍처 선택

## Status
Accepted

## Date
2026-02

## Context
26년간 축적된 약 65,000개 문서(HWP 59%, Office, PDF)를 분석하여
과거 프로젝트 아이디어의 MSP 전환 가능성을 평가해야 합니다.

요구사항:
- 한국어 문서(HWP 포함) 처리 필수
- 메타데이터 기반 필터링 (프로젝트별, 연도별, 문서 유형별)
- 자연어 질의 기반 분석
- 로컬 개발 환경 우선 (Docker)

## Considered Alternatives

### Alternative 1: LangChain + FAISS
- Pros: 경량, 빠른 프로토타이핑
- Cons: 메타데이터 필터링 제한, 영속성 관리 어려움

### Alternative 2: LlamaIndex + Weaviate
- Pros: 문서 파이프라인 특화, 하이브리드 검색
- Cons: 추가 인프라 필요, 러닝 커브

### Alternative 3: FastAPI + ChromaDB/pgvector (자체 구현) ✅ Selected
- Pros: 완전한 커스터마이징, 기존 PostgreSQL 인프라 활용, HWP 변환기 직접 제어
- Cons: 초기 개발 비용 높음

## Decision
FastAPI 기반 자체 파이프라인을 구축합니다.

### Specific Decision Details
- 개발 시 ChromaDB, 운영 시 PostgreSQL + pgvector
- HWP 변환: hwp5txt 우선 → LibreOffice CLI 폴백
- 임베딩: OpenAI text-embedding-3-large (한국어 성능 우수)
- LLM: Anthropic Claude (분석 품질)
- 도메인 분리 구조: ingestion / embedding / vectordb / rag

## Results

### Positive Results
- HWP 변환 전략을 세밀하게 제어 가능
- 프로젝트별 메타데이터 체계 직접 설계
- 기존 MCP 인프라(PostgreSQL, Docker)와 자연스러운 통합

### Negative Results (Trade-offs)
- LangChain/LlamaIndex 대비 초기 구현 비용 높음
- 직접 구현한 만큼 유지보수 부담

### Future Considerations
- 대규모 처리 시 Celery/Redis 기반 비동기 큐 도입 검토
- 하이브리드 검색(BM25 + 벡터) 추가 검토
