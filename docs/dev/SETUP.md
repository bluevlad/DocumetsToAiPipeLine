# 개발 환경 설정

## 필수 요구사항

- Python 3.12+
- Docker Desktop
- Git

## 설치 방법

### 1. 저장소 클론

```bash
git clone <repository-url>
cd DocumetsToAiPipeLine
```

### 2. 가상 환경 생성

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac

pip install -r requirements.txt
```

### 3. 환경 변수 설정

```bash
cp .env.example .env.local
# .env.local 파일 편집: API 키 등 설정
```

### 4. 로컬 실행

```bash
# 직접 실행
uvicorn app.main:app --reload --port 9060

# Docker 실행
docker compose -f docker-compose.local.yml up -d
```

### 5. 접속 확인

```bash
curl http://localhost:9060/health
# {"status": "ok", "version": "0.1.0"}
```

## 환경 변수

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `DOCUMENTS_ROOT` | 문서 소스 경로 | `./data/documents` |
| `DATABASE_URL` | PostgreSQL 연결 | `postgresql://postgres:postgres@localhost:5432/rag_pipeline` |
| `VECTOR_DB_TYPE` | 벡터DB 유형 | `chroma` |
| `OPENAI_API_KEY` | OpenAI API 키 | (필수) |
| `ANTHROPIC_API_KEY` | Anthropic API 키 | (필수) |

## 테스트

```bash
pytest tests/
pytest tests/unit/ -v
pytest tests/integration/ -v
```

## Docker 구성

| 서비스 | 포트 | 설명 |
|--------|------|------|
| app | 9060 | FastAPI 애플리케이션 |
| db | 5442 | PostgreSQL + pgvector |
