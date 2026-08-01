# 임베딩 / LLM 옵션 — 로컬 vs 유료 API 비교 참조

> 이 프로젝트(DocumetsToAiPipeLine)의 레거시 인덱싱(Phase 1~4)에서 **실제 사용된 옵션**과
> **제안만 되고 실행하지 않은 옵션**을 모두 정리한 참조 문서. 향후 모델·공급자 전환 시 기준으로 활용.
> 마지막 갱신: 2026-04-21

## 목차

1. [현재 사용 중 — 로컬 임베딩](#1-현재-사용-중--로컬-임베딩)
2. [미실행 제안 — OpenAI 임베딩 API](#2-미실행-제안--openai-임베딩-api)
3. [Claude API 의 포지션](#3-claude-api-의-포지션)
4. [Local LLM (Ollama) 옵션](#4-local-llm-ollama-옵션)
5. [비교 매트릭스](#5-비교-매트릭스)
6. [선택 가이드 (언제 어느 것)](#6-선택-가이드-언제-어느-것)
7. [전환 방법 (settings / 코드 변경)](#7-전환-방법)
8. [실행 cheat sheet](#8-실행-cheat-sheet)

---

## 1. 현재 사용 중 — 로컬 임베딩

### 상태
✅ **실제 실행·검증 완료** (Phase 1 파일럿 10건 + Phase 2 전체 2,001건 / 270,266 청크)

### 설정

| 항목 | 값 |
|------|-----|
| 공급자 | `sentence-transformers` (로컬) |
| 모델 | `paraphrase-multilingual-MiniLM-L12-v2` |
| 차원 | 384 |
| 디바이스 | CPU (이 개발 PC에 GPU 없음) |
| 배치 크기 | 32~64 |
| 비용 | **$0** (완전 무료) |

### 실측 성능 (이 프로젝트)

| 지표 | 값 |
|------|-----|
| 모델 최초 로드 | ~20초 (HuggingFace 캐시 확인 포함) |
| Batch 10건 (짧은 텍스트) | 0.04초 |
| 파일럿 10건 (191 청크) | 5.8초 |
| 전체 2,001건 (270,266 청크) | **4시간 22분** |
| 전체 스토리지 (torch + transformers + 모델 캐시) | ~2GB |

### 장점

- 완전 무료, API 호출 제한 없음
- 네트워크 없이 작동 (오프라인·폐쇄망 OK)
- 데이터가 외부로 나가지 않음 (개인정보/계약/내부문서에 안전)
- 스케일 제한 없음 — 쿼터 걱정 없이 대용량 반복 처리 가능

### 단점

- **CPU 기준 느림** — GPU 없으면 대용량 배치에 시간 소요
- **한국어 검색 품질은 중상** (MiniLM 은 일반 목적 경량 모델)
  - 도메인 특화 뉘앙스(회계/법률/의학 등)에서는 OpenAI 대비 Top-k 품질 차이
- 초기 설치 필요 (torch + sentence-transformers ≈ 2GB)

### 발생한 이슈

- **대용량 xlsx 임베딩 batch 초과**: 단일 문서에서 5,000~37,000 청크가 생성되면
  `sentence-transformers.encode` 내부 한도 초과로 ValueError.
  → Phase 2 37건 실패 원인. 해결: `batch_size=8`로 낮추거나 문서 당 청크 상한 부여.

### 향후 품질 업그레이드 옵션

**로컬 그대로 유지하면서 품질을 높이고 싶다면:**

- `BAAI/bge-m3` (한국어 품질 ★★★★★, 1024dim, CPU ~3배 느림)
- `upskyy/bge-m3-korean` (프로젝트 기본값, 한국어 미세조정)
- `jhgan/ko-sroberta-multitask` (한국어 전용)

차원을 늘리면 ChromaDB 컬렉션 재생성 필요.

---

## 2. 미실행 제안 — OpenAI 임베딩 API

### 상태
❌ **미실행** — OpenAI 계정의 무료 크레딧이 소진돼(`insufficient_quota` 에러) 파일럿에서 포기.
이후 로컬로 전환해 파이프라인 완주.

### 설정 (실행했다면)

| 항목 | 값 |
|------|-----|
| 공급자 | OpenAI API |
| 모델 | `text-embedding-3-large` |
| 차원 | 3072 (축소 가능: 1536, 1024, 512) |
| 단가 | **$0.13 / 1M tokens** |
| 환경변수 | `OPENAI_API_KEY` |

### 예상 비용 (이 프로젝트 기준)

| 범위 | 토큰 추정 | 비용 (USD) | 비용 (KRW) |
|------|---------|-----------|-----------|
| 파일럿 10건 (190K tokens) | 0.19M | $0.025 | ~35원 |
| 전체 2,135건 (약 40M tokens) | 40M | $5.20 | ~7,200원 |

→ **Tier 1 진입($5 결제)만으로 전체 인덱싱 여유.**

### 예상 성능

- **분당 3,000 요청 / 토큰 1M** (Tier 1) — 이 프로젝트의 270,266 청크는 쿼터 대비 여유
- 실측 경험(다른 프로젝트): 270K 청크 ≈ **10~30분** (네트워크 대기 포함)
- → 로컬 CPU 대비 **약 10배 빠름**

### 장점

- 한국어 포함 50+ 언어에서 현시점 최상위 품질
- 네트워크만 되면 설치 불필요
- 대용량 배치에 최적화된 API 배치 엔드포인트 제공

### 단점

- 비용 발생 (무료 아님)
- 외부 전송 — 민감 데이터는 계약·정책 확인 필요
- 쿼터 관리 필요 (Tier 상향 자동 아님, 결제 이력으로만 승급)
- 인터넷 필수 (폐쇄망 불가)

### 쿼터/과금 요약

| Tier | 조건 | text-embedding-3-large 한도 |
|------|------|---------------------------|
| Free | 결제수단만 등록 | RPM 100 / TPM 40K |
| Tier 1 | $5+ 1회 결제 | RPM 3,000 / TPM 1M |
| Tier 2 | $50+ 누적 & 7일 경과 | RPM 5,000 / TPM 1M |
| Tier 3~5 | $100~$1,000+ 누적 | 점진 상향 |

> ⚠️ **무료 크레딧은 매일 리셋 안 됨.** 신규 가입 시 $5 일회성 크레딧(3개월 만료).
> 이후에는 결제 필수.

---

## 3. Claude API 의 포지션

### 결론
❌ **Claude 는 임베딩 API 가 없다.** 어떤 구독·모델도 마찬가지.

### 오해 방지

| 질문 | 답 |
|------|----|
| Claude Opus/Sonnet 모델로 임베딩 가능? | ❌ 텍스트 생성만 |
| Claude Max 구독이면 임베딩 무료? | ❌ 임베딩 엔드포인트 자체 없음 |
| Claude Max 로 이 프로젝트 API 호출? | ❌ Max 는 Claude Code CLI 용이고, Python SDK 직접 호출은 별도 결제 |

### Claude 가 실제로 쓸 수 있는 곳 (이 프로젝트 기준)

**임베딩 대용이 아니라 생성·판단·요약 작업에만 사용:**

- 파일럿 MD 요약을 LLM 요약으로 고도화 (현재는 구조 dump)
- Phase 3 canonical 통합 시 유사도 판정 보조 (LLM-as-judge)
- Phase 4 MSA rationale 자동 생성
- Uncategorized 32건의 내용 기반 재분류
- 엔티티 추출 정제 (regex 휴리스틱 → LLM)

→ **Anthropic API 키**(`.env` 의 `ANTHROPIC_API_KEY`)로 호출. console.anthropic.com 에서 크레딧 충전 필요.

---

## 4. Local LLM (Ollama) 옵션

### 상태
❌ **미설치·미실행** — 참조용.

### 사용처

임베딩이 아닌 **생성 작업**의 로컬 대안. 인터넷 없이 요약·분류·판정.

### 후보 모델

| 모델 | 크기 | CPU 1토큰 | 한국어 품질 | 용도 |
|------|-----|---------|-----------|-----|
| `qwen2.5:7b` | ~5GB | 200ms | ★★★★ | 요약·분류 기본 추천 |
| `llama3.1:8b` | ~5GB | 250ms | ★★★ | 영문 강점 |
| `gemma2:9b` | ~6GB | 300ms | ★★★★ | 균형 |
| `qwen2.5:14b` | ~9GB | 500ms+ | ★★★★★ | GPU 필요 |

### 실용성

- 1건 요약(1~2K 토큰 입력 → 500 토큰 출력) = **수십 초 ~ 수 분** (CPU 기준)
- 수천 건 배치는 **비현실적** (GPU 없이는)
- Claude API 대비: 속도 10~100배 느림, 품질 체감 2~3배 낮음

### 설치·실행 예시 (미실행)

```bash
# 설치
winget install Ollama.Ollama          # Windows
# brew install ollama                 # macOS

# 모델 받기
ollama pull qwen2.5:7b

# 서버 기동 (백그라운드)
ollama serve

# Python 통합 예 (LangChain 대신 httpx)
curl http://localhost:11434/api/generate -d '{"model":"qwen2.5:7b","prompt":"요약: ..."}'
```

---

## 5. 비교 매트릭스

### 5.1 임베딩 옵션 (이 프로젝트 기준)

| 항목 | 로컬 MiniLM (실제) | 로컬 BGE-m3 (권장 업그레이드) | OpenAI 3-large (제안) |
|------|------------------|----------------------------|---------------------|
| 실행 여부 | ✅ 실행 | 💡 제안 | 💡 제안 (쿼터 소진) |
| 설치 | torch + st ≈ 2GB | torch + st ≈ 2GB | API 키만 |
| 네트워크 | ❌ 필요 없음 | ❌ 필요 없음 | ✅ 필수 |
| 차원 | 384 | 1024 | 3072 (축소 가능) |
| 전체 270K 청크 소요 | **4시간 22분** (CPU) | 약 12~15시간 (CPU) | **10~30분** (API) |
| 비용 | $0 | $0 | ~$5.2 (7,200원) |
| 한국어 검색 품질 | ★★★ (중상) | ★★★★★ | ★★★★★ |
| 데이터 외부 전송 | 없음 | 없음 | 있음 (OpenAI 서버) |
| 쿼터·레이트 한계 | 없음 | 없음 | Tier 별 RPM/TPM |
| 폐쇄망 가능 | ✅ | ✅ | ❌ |

### 5.2 생성 LLM 옵션

| 항목 | Claude API (기존 키) | Local Ollama (미실행) | OpenAI GPT |
|------|-------------------|--------------------|-----------|
| 실행 여부 | ❌ (Phase 1~4 에서 미사용) | ❌ | ❌ |
| 비용 | 유료 (입력 $3~15/1M, 출력 $15~75/1M) | $0 | 유료 |
| 설치 | SDK 만 | Ollama 바이너리 + 모델 5~10GB | SDK 만 |
| 네트워크 | 필수 | 불필요 | 필수 |
| 한국어 품질 | ★★★★★ | ★★★~★★★★ | ★★★★ |
| 배치 수천 건 실용성 | 적합 (Batch API 활용) | 부적합 (CPU) | 적합 (Batch API) |
| 폐쇄망 가능 | ❌ | ✅ | ❌ |

### 5.3 3가지 경로 (이 프로젝트에 제안된)

| 경로 | 임베딩 | 요약/판정 LLM | 총 예상 비용 | 총 예상 시간 (전체 2,135건) | 품질 |
|------|-------|-------------|----------|-----------------------|-----|
| **A. 완전 무료** (현재) | 로컬 MiniLM | (생략) | **$0** | 4.5시간 | ★★★ |
| **B. 하이브리드** (권장) | 로컬 BGE-m3 | Claude API | ~$5~15 | 12시간 + LLM 별도 | ★★★★★ |
| **C. 완전 유료** | OpenAI embed | Claude API | ~$10~25 | 30분 + LLM 별도 | ★★★★★ |

---

## 6. 선택 가이드 (언제 어느 것)

### 경로 A — 로컬만 (현재 상태)

**선택 기준:**
- 오프라인·폐쇄망 요구
- 데이터 외부 전송 금지 (계약/규제)
- 일회성·탐색적 인덱싱 (품질 보다 속도·비용 중요)
- 반복·재실행 많음 (쿼터 걱정 없음)

**지양해야 할 때:**
- 고도의 도메인 특화 검색 (법률/의학/회계)
- 수만~수십만 청크의 빠른 초기 구축 필요

### 경로 B — 로컬 임베딩 + Claude 요약 (권장)

**선택 기준:**
- 품질은 높이되 임베딩 비용은 피하고 싶음
- 요약·분류·Q&A 같은 "LLM 본업" 만 유료로
- 한 번 빌드된 벡터 DB 를 반복 사용

**구현:**
- 임베딩: 로컬 BGE-m3 (업그레이드)
- Phase 3 canonical 판정, Phase 4 rationale 생성 등 Claude API

### 경로 C — 완전 유료

**선택 기준:**
- 시간이 곧 비용 (프로덕션 SLA)
- 최고 품질 필요
- 예산 넉넉 (개인 $10, 팀 수십~수백 달러)

**주의:**
- OpenAI Tier 1 진입 후 대용량은 Batch API (50% 할인) 활용

---

## 7. 전환 방법

### 7.1 로컬 → OpenAI 임베딩 전환

**① `.env` 변경:**

```bash
# 이전
EMBEDDING_PROVIDER=local
EMBEDDING_LOCAL_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
EMBEDDING_DIMENSION=384

# 이후
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-large
EMBEDDING_DIMENSION=3072
OPENAI_API_KEY=sk-...
```

**② ChromaDB 컬렉션 재생성 (차원 변경 시 필수)**

`legacy_docs` 컬렉션은 384dim 으로 생성됐으므로 3072dim 벡터 insert 시 오류.
→ 새 컬렉션 사용 (예: `legacy_docs_openai`) 또는 기존 삭제 후 재구축.

**③ 러너 인자 또는 코드:**

```bash
# Phase 1 파일럿
venv/Scripts/python.exe scripts/legacy_pilot/run_pilot.py --embedding-provider openai

# Phase 2 전체
# settings 만 바꾸면 자동 반영 (DocumentEmbedder 는 settings.EMBEDDING_PROVIDER 를 읽음)
venv/Scripts/python.exe scripts/legacy_full_ingest/run.py
```

### 7.2 로컬 MiniLM → 로컬 BGE-m3 업그레이드

```bash
# .env 변경
EMBEDDING_LOCAL_MODEL=upskyy/bge-m3-korean
EMBEDDING_DIMENSION=1024

# 모델 최초 로드 시 HuggingFace 에서 ~2GB 다운로드
# 기존 ChromaDB 컬렉션은 차원 달라 재구축 필요
```

### 7.3 Claude API 요약 추가

현재 코드에는 LLM 요약 단계 없음. 추가하려면:

```python
# app/legacy/llm_summarizer.py (신규)
from anthropic import AsyncAnthropic
from app.core.config import settings

client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

async def summarize(chunks: list[str]) -> str:
    resp = await client.messages.create(
        model=settings.LLM_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": f"요약: {chunks}"}],
    )
    return resp.content[0].text
```

예상 비용 (이 프로젝트 270K 청크를 문서 단위 2,001건으로 요약):
- 평균 요약 당 입력 5K + 출력 500 tokens
- Claude Sonnet 4.5: $3/1M in + $15/1M out
- 2,001 × (5K × $3/1M + 500 × $15/1M) ≈ **$45** (약 62,000원)

→ 전체 요약은 비쌈. **P0/P1 canonical 30건만** 타겟하면 ~$1 이내.

---

## 8. 실행 cheat sheet

### 현재 (로컬 MiniLM) 그대로 사용

```bash
cd C:/GIT/DocumetsToAiPipeLine
venv/Scripts/python.exe scripts/legacy_pilot/run_pilot.py           # 파일럿
venv/Scripts/python.exe scripts/legacy_full_ingest/run.py            # 전체
venv/Scripts/python.exe scripts/legacy_phase3/build_canonical.py     # canonical
```

### OpenAI 로 전환

```bash
# .env 수정 후
venv/Scripts/python.exe scripts/legacy_pilot/run_pilot.py --embedding-provider openai
```

### 비용 실측 — OpenAI

```bash
# 토큰 수 미리 계산 (tiktoken)
venv/Scripts/python.exe -c "
import tiktoken
enc = tiktoken.encoding_for_model('text-embedding-3-large')
# 청크 DB 에서 샘플 100건 꺼내서 토큰 합 측정
"
```

### 상태 확인

```bash
# ChromaDB 컬렉션 벡터 수
venv/Scripts/python.exe -c "
import chromadb
from chromadb.config import Settings as C
cli = chromadb.PersistentClient(path='./chroma_data', settings=C(anonymized_telemetry=False))
for col in cli.list_collections():
    print(col.name, col.count())
"

# SQLite 메타
venv/Scripts/python.exe -c "
import sqlite3
db = sqlite3.connect('data/legacy/legacy_pilot.db')
for row in db.execute('SELECT status, COUNT(*) FROM legacy_document GROUP BY status'):
    print(row)
"
```

---

## 참고: 이 프로젝트의 실제 선택 이유

| 단계 | 선택 | 이유 |
|------|------|------|
| 초기 Phase 1 | OpenAI 시도 | 속도·품질 최상, 파일럿 $0.025 예상 |
| Phase 1 중단 | OpenAI 실패 | 계정 무료 크레딧 소진 (`insufficient_quota`) |
| Phase 1 재실행 | 로컬 MiniLM 채택 | 무료·즉시 사용·충분한 품질. torch+st 설치 후 5.8초 |
| Phase 2 | 로컬 유지 | 파일럿 성공 확인. 전체 4.5시간 완주 (정숙시간 전) |
| Phase 3~4 | 로컬 유지 | canonical 임베딩·검색에 동일 모델 재사용 |

**변곡점:** 프로덕션 품질 검색이 필요해지면 경로 B(로컬 BGE-m3 + Claude 요약)로 전환 권장.
예산 허용되면 경로 C(OpenAI 임베딩)로 품질·속도 양쪽 극대화.
