"""요구사항 유형별 패턴 라이브러리 생성기.

_extracted/*.json 의 전체 요구사항을 분석하여
  1) 유형구분별 분포/대표 사례
  2) 기능 주제(인증/검색/결재/연계 등) 클러스터 — 반복 출현 패턴
  3) 신규 AI 시스템 시사점(재사용 모듈 후보)
를 docs/requirements/_patterns.md 로 생성한다.

주제 분류는 큐레이션된 SI 패턴 키워드 매칭(결정적·설명가능)을 사용한다.

Usage:
  .venv/bin/python scripts/requirements/analyze_patterns.py
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS_REQ = ROOT / "docs" / "requirements"
EXTRACTED_DIR = DOCS_REQ / "_extracted"

# ── SI 공통 기능 주제 → 키워드 ───────────────────────────────
THEMES: dict[str, list[str]] = {
    "인증/로그인": ["로그인", "인증", "sso", "비밀번호", "패스워드", "본인확인", "인증서", "싱글사인온"],
    "권한/접근제어": ["권한", "접근통제", "접근 통제", "메뉴권한", "메뉴 권한", "롤", "접근권한"],
    "사용자/회원관리": ["회원", "사용자관리", "사용자 관리", "가입", "탈퇴", "회원관리", "사원관리", "조직관리"],
    "검색/조회": ["검색", "조회", "찾기", "필터", "검색조건", "검색 조건"],
    "통계/리포트/대시보드": ["통계", "리포트", "보고서", "현황", "집계", "그래프", "차트", "대시보드", "분석화면"],
    "결재/승인": ["결재", "승인", "반려", "결재선", "전자결재", "상신"],
    "게시판/콘텐츠": ["게시판", "공지", "게시물", "자료실", "faq", "q&a", "콘텐츠", "컨텐츠", "게시"],
    "파일/문서관리": ["파일", "첨부", "문서관리", "업로드", "다운로드", "문서 관리", "산출물관리"],
    "알림/메일/SMS": ["알림", "메일", "이메일", "sms", "문자", "푸시", "발송", "안내메일"],
    "코드/기준정보": ["공통코드", "기준정보", "코드관리", "코드 관리", "분류관리", "분류 관리"],
    "일정/예약/스케줄": ["일정", "캘린더", "예약", "스케줄", "스케쥴"],
    "결제/정산/매출": ["결제", "정산", "매출", "환불", "수납", "과금", "요금", "카드"],
    "데이터연계/인터페이스": ["연계", "인터페이스", "eai", "api", "연동", "전송", "타시스템", "타 시스템"],
    "데이터이관/마이그레이션": ["마이그레이션", "이관", "데이터변환", "데이터 변환", "적재", "초기데이터"],
    "보안/감사/암호화": ["암호화", "보안", "감사", "접근기록", "로그기록", "위변조", "전자서명"],
    "성능/가용성/백업": ["성능", "응답시간", "동시접속", "처리량", "이중화", "백업", "복구", "무중단"],
    "교육/학습(LMS)": ["강의", "수강", "학습", "과정", "평가", "시험", "출결", "진도", "콘텐츠 학습", "이러닝"],
    "통합/포털/메인": ["통합", "포털", "메인화면", "메인 화면", "단일화면", "허브"],
    "모바일/반응형": ["모바일", "스마트폰", "반응형", "앱(", "어플"],
    "다국어/국제화": ["다국어", "국제화", "영문", "언어선택", "다국어지원"],
}

TYPE_ORDER = [
    "기능", "비기능-성능", "비기능-보안", "비기능-규제", "비기능-가용성",
    "데이터", "인터페이스", "운영관리", "제약사항", "기타",
]


def load_all() -> list[dict]:
    items = []
    for f in sorted(EXTRACTED_DIR.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        for r in d["requirements"]:
            items.append({
                "name": r.get("req_name", ""),
                "detail": r.get("req_detail", ""),
                "type": r.get("req_type", "기타"),
                "strategy": r.get("strategy", ""),
                "loc": r.get("source_loc", ""),
                "project": d["project_title"],
                "project_slug": d["project_slug"],
                "domain": d.get("domain", "etc"),
                "source_file": d["source_file"],
            })
    return items


def classify_themes(text: str) -> list[str]:
    t = text.lower()
    return [theme for theme, kws in THEMES.items() if any(k in t for k in kws)]


def esc(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ").strip()


def has_strategy(r: dict) -> bool:
    s = r.get("strategy", "")
    return bool(s) and s != "(원문 미기재)"


def main() -> int:
    items = load_all()
    if not items:
        print("[WARN] _extracted/ 비어있음")
        return 1

    n = len(items)
    type_counter = Counter(r["type"] for r in items)

    # 주제 집계
    theme_items: dict[str, list[dict]] = defaultdict(list)
    for r in items:
        for th in classify_themes(r["name"] + " " + r["detail"]):
            theme_items[th].append(r)

    theme_stats = []
    for th, rs in theme_items.items():
        projects = {r["project"] for r in rs}
        theme_stats.append({
            "theme": th, "count": len(rs), "projects": len(projects),
            "project_set": projects, "items": rs,
            "n_strategy": sum(1 for r in rs if has_strategy(r)),
        })
    # 반복 출현도: 프로젝트 확산 우선, 그다음 건수
    theme_stats.sort(key=lambda x: (x["projects"], x["count"]), reverse=True)

    L: list[str] = []
    L.append("---\ntitle: 요구사항 유형별 패턴 라이브러리\ndoc_type: requirements-patterns\n---\n")
    L.append("# 요구사항 유형별 패턴 라이브러리\n")
    L.append(
        "26년치 프로젝트 요구사항 정의서 "
        f"**{n:,}건**(20개 프로젝트)을 유형구분과 기능 주제로 분석한 패턴 라이브러리. "
        "신규 AI 시스템 설계 시 **반복 출현 요구사항 = 재사용 모듈 후보**, "
        "**검증된 대응전략 = 구현방안 출발점**으로 활용한다.\n")

    # 1. 유형구분 분포
    L.append("## 1. 유형구분 분포\n")
    L.append("| 유형구분 | 건수 | 비율 |")
    L.append("|---------|------|------|")
    for t in TYPE_ORDER:
        c = type_counter.get(t, 0)
        if c:
            L.append(f"| {t} | {c:,} | {c / n * 100:.1f}% |")
    L.append("")

    # 2. 반복 출현 기능 주제 (패턴 랭킹)
    L.append("## 2. 반복 출현 기능 주제 (패턴 랭킹)\n")
    L.append("프로젝트 확산도(몇 개 프로젝트에서 반복되는가) 기준 정렬. "
             "확산도가 높을수록 도메인 무관 **공통 재사용 모듈**일 가능성이 크다.\n")
    L.append("| 순위 | 주제 | 출현 프로젝트 수 | 요구사항 수 | 대응전략 보유 |")
    L.append("|------|------|----------------|-----------|-------------|")
    for i, s in enumerate(theme_stats, 1):
        L.append(f"| {i} | {s['theme']} | {s['projects']}/20 | {s['count']} | {s['n_strategy']} |")
    L.append("")

    # 3. 주제별 상세 (대표 사례 + 대응전략)
    L.append("## 3. 주제별 패턴 상세\n")
    for s in theme_stats:
        L.append(f"### {s['theme']}  ·  {s['count']}건 / {s['projects']}개 프로젝트\n")
        proj_list = ", ".join(sorted(s["project_set"])[:8])
        if len(s["project_set"]) > 8:
            proj_list += f" 외 {len(s['project_set']) - 8}개"
        L.append(f"- **출현 프로젝트**: {proj_list}")
        # 대표 사례: 대응전략 있는 것 우선, 길이 있는 detail 우선
        examples = sorted(s["items"], key=lambda r: (has_strategy(r), len(r["detail"])), reverse=True)[:5]
        L.append("\n| 요구사항명 | 요구사항 | 유형 | 대응전략 | 출처 |")
        L.append("|-----------|---------|------|---------|------|")
        for r in examples:
            src = r["source_file"] + (f" #{r['loc']}" if r["loc"] else "")
            L.append(f"| {esc(r['name'])} | {esc(r['detail'])[:80]} | {esc(r['type'])} "
                     f"| {esc(r['strategy'])[:50]} | {esc(src)[:45]} |")
        L.append("")

    # 4. AI 시스템 시사점
    top = theme_stats[:8]
    L.append("## 4. 신규 AI 시스템 방향성 시사점\n")
    L.append("패턴 분석에서 도출되는 설계 방향:\n")
    L.append("**A. 공통 재사용 모듈 (확산도 상위 — 도메인 무관 반복)**")
    for s in top:
        L.append(f"- **{s['theme']}** — {s['projects']}개 프로젝트 반복. 신규 시스템에서도 표준 모듈로 우선 설계 권장.")
    L.append("")
    L.append("**B. 대응전략 데이터가 얕은 영역 (설계서 보강 필요)**")
    thin = [s for s in theme_stats if s["count"] >= 20 and s["n_strategy"] / max(s["count"], 1) < 0.1]
    for s in thin[:6]:
        L.append(f"- **{s['theme']}** — {s['count']}건 중 대응전략 명시 {s['n_strategy']}건. "
                 f"요구사항 정의서엔 What만 있어 How는 설계서 추가 추출 필요.")
    L.append("")
    L.append("**C. AI 활용 포인트**")
    L.append("- 신규 요구사항 입력 → RAG로 위 주제별 과거 사례·대응전략 자동 매칭 (구현 완료)")
    L.append("- 유형구분 자동 분류기로 신규 요구사항 정의서 작성 시 누락 유형(보안/규제/가용성) 점검")
    L.append("- 확산도 높은 주제는 신규 시스템 요구사항 체크리스트의 기본 항목으로 제안")
    L.append("")

    out = DOCS_REQ / "_patterns.md"
    out.write_text("\n".join(L), encoding="utf-8")
    print(f"[DONE] {out} 생성 ({n:,}건 분석, 주제 {len(theme_stats)}개)")
    print("상위 패턴:", ", ".join(f"{s['theme']}({s['projects']})" for s in theme_stats[:6]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
