# API Change History

[Semantic Versioning](https://semver.org/) 을 따릅니다.

## [Unreleased]

### Added
- `GET /health` - 헬스체크
- `POST /api/v1/ingest/file` - 단일 파일 수집
- `POST /api/v1/ingest/directory` - 디렉토리 일괄 수집
- `GET /api/v1/ingest/status` - 수집 상태 조회
- `POST /api/v1/search/` - 벡터 유사도 검색
- `POST /api/v1/analyze/` - RAG 기반 문서 분석
- `POST /api/v1/analyze/msp-evaluation` - MSP 전환 가능성 평가
