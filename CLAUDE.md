# DocumetsToAiPipeLine 프로젝트 설정

## 프로젝트 개요
26년간(1999-2025) 축적된 IT 프로젝트 문서(약 65,000개)를 RAG DB로 구축하여,
과거 아이디어의 MSP 서비스 전환 가능성을 분석하는 파이프라인.

## 기술 스택
- Backend: Python 3.12 / FastAPI
- Vector DB: ChromaDB (dev) → PostgreSQL + pgvector (prod)
- Embedding: OpenAI text-embedding-3-large
- LLM: Anthropic Claude (claude-sonnet-4-5)
- Container: Docker Compose

## 문서 소스
- 경로: `.env`의 `DOCUMENTS_ROOT`로 지정 (git 외부, 읽기 전용)
- 핵심 포맷: HWP, DOC, PPT, XLS, PDF, TXT (HWP가 약 59%로 최다)

## 빌드/실행 명령
- 로컬 실행: `uvicorn app.main:app --reload --port 9060`
- Docker: `docker compose -f docker-compose.local.yml up -d`
- 테스트: `pytest tests/`

## 환경 구분
- 개발 환경: `.env.local`, `docker-compose.local.yml`
- 운영 환경: `.env.production`, `docker-compose.production.yml`

## Do NOT
- .env, .env.local, .env.production 파일을 git에 커밋하지 않음
- 문서 원본(`DOCUMENTS_ROOT`)을 수정하지 않음 (읽기 전용)
- API 키를 코드에 하드코딩하지 않음
- 분석 대상 문서에서 파생된 산출물(고객사·개인 정보 포함)을 이 저장소에 커밋하지 않음 — private 저장소에서 관리

## Fix 커밋 오류 추적

> 상세: [FIX_COMMIT_TRACKING_GUIDE.md](https://github.com/bluevlad/Claude-Opus-bluevlad/blob/main/standards/git/FIX_COMMIT_TRACKING_GUIDE.md) | [ERROR_TAXONOMY.md](https://github.com/bluevlad/Claude-Opus-bluevlad/blob/main/standards/git/ERROR_TAXONOMY.md)

`fix:` 커밋 시 footer에 오류 추적 메타데이터를 **필수** 포함합니다.

### 이 프로젝트에서 자주 발생하는 Root-Cause

| Root-Cause | 설명 | 예방 |
|-----------|------|------|
| `env-assumption` | Docker 내/외부 경로, 환경변수 가정 | Settings 클래스에서 필수값 검증, 기본값 금지 |
| `import-error` | 패키지 import 경로 오류, 상대/절대 경로 혼동 | `__init__.py` 확인, 절대 import 사용 |
| `null-handling` | Optional 필드 None 미처리 | Pydantic `Optional[T]` + 기본값 명시 |
| `type-mismatch` | SQLAlchemy 모델 ↔ Pydantic 스키마 타입 불일치 | `model_validate()` 사용, from_attributes=True |
| `async-handling` | await 누락, 동기/비동기 혼용 | async def에서 동기 DB 호출 금지, run_in_executor 사용 |
| `db-migration` | Alembic 마이그레이션 누락/충돌 | 스키마 변경 시 반드시 `alembic revision --autogenerate` |

### 예시

```
fix(api): 알레르기 성분 조회 시 None 응답 처리

- ingredient가 Optional인데 None 체크 없이 .name 접근하여 AttributeError 발생
- None일 때 빈 문자열 반환하도록 수정

Root-Cause: null-handling
Error-Category: logic-error
Affected-Layer: backend/api
Recurrence: first
Prevention: Optional 필드 접근 전 반드시 None 체크, or 연산자 활용

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
```
