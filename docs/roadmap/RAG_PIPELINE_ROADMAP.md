# RAG Pipeline Roadmap

## Overview
26년간의 IT 프로젝트 문서를 RAG DB로 구축하여 MSP 서비스 전환 아이디어를 발굴.

### Goals
- 약 65,000개 문서의 텍스트 변환 및 벡터DB 적재
- 자연어 질의 기반 프로젝트 분석
- MSP 서비스 전환 가능성 자동 평가

---

## Phase 1: 파이프라인 PoC

### Goals
소규모 샘플(100개)로 전체 파이프라인 검증

### Tasks
- [ ] HWP 변환기 구현 (hwp5txt + LibreOffice 폴백)
- [ ] Office 변환기 구현 (python-docx, python-pptx, openpyxl)
- [ ] PDF 변환기 구현 (PyMuPDF)
- [ ] 텍스트 청킹 구현 (RecursiveCharacterTextSplitter)
- [ ] ChromaDB 연동 및 벡터 저장
- [ ] 기본 검색 API 동작 확인

### Deliverables
- 동작하는 PoC 파이프라인
- HWP 변환 성공률 측정 리포트

---

## Phase 2: 전체 문서 적재

### Goals
전체 문서(65K+) 처리

### Tasks
- [ ] 병렬 처리 (asyncio / 멀티프로세싱)
- [ ] 진행률 추적 및 대시보드
- [ ] 에러 핸들링 및 재시도 로직
- [ ] 메타데이터 정규화 (프로젝트명, 연도, 카테고리)

### Deliverables
- 전체 문서 벡터DB 적재 완료
- 수집 통계 리포트

---

## Phase 3: RAG 질의 엔진

### Goals
자연어 질의로 문서 분석 및 인사이트 도출

### Tasks
- [ ] Retriever + Generator 통합
- [ ] MSP 평가 특화 프롬프트 설계
- [ ] 프로젝트별 필터링 검색
- [ ] 응답 품질 평가 (human-in-the-loop)

### Deliverables
- 동작하는 RAG 질의 API
- MSP 전환 평가 보고서 자동 생성

---

## Phase 4: 프로덕션 전환

### Tasks
- [ ] ChromaDB → PostgreSQL + pgvector 마이그레이션
- [ ] Docker Compose 운영 설정
- [ ] 모니터링 (Sentry MCP 연동)
- [ ] 보안 점검 (API 인증, CORS)

---

## Change History

| 날짜 | 변경 내용 |
|------|----------|
| 2026-02-16 | 최초 작성 |
