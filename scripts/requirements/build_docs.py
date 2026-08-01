"""Phase 3 — 추출 JSON → 프로젝트별 정리 .md + 마스터 _index.md.

docs/requirements/_extracted/*.json 을 읽어
  - docs/requirements/<slug>.md   : 프로젝트별 요구사항 5필드 표
  - docs/requirements/_index.md   : 전체 마스터 인덱스 (유형/프로젝트 통계 + 링크)
를 생성한다.

Usage:
  .venv/bin/python scripts/requirements/build_docs.py
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DOCS_REQ = ROOT / "docs" / "requirements"
EXTRACTED_DIR = DOCS_REQ / "_extracted"
SLUGS = yaml.safe_load((ROOT / "docs" / "projects" / "_slugs.yaml").read_text(encoding="utf-8"))


def md_escape(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ").strip()


def load_extractions() -> dict[str, list[dict]]:
    """slug → [extraction json, ...]"""
    by_slug: dict[str, list[dict]] = defaultdict(list)
    for f in sorted(EXTRACTED_DIR.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        by_slug[data["project_slug"]].append(data)
    return by_slug


def build_project_doc(slug: str, docs: list[dict]) -> tuple[str, int, Counter]:
    title = docs[0]["project_title"]
    domain = docs[0].get("domain", "etc")
    type_counter: Counter = Counter()
    rows_md: list[str] = []
    sources: list[str] = []
    rid = 0
    for d in sorted(docs, key=lambda x: x["source_file"]):
        src_file = d["source_file"]
        if d["requirements"]:
            sources.append(d["source_rel"])
        for r in d["requirements"]:
            rid += 1
            loc = r.get("source_loc", "")
            src = f"{src_file}" + (f" #{loc}" if loc else "")
            type_counter[r.get("req_type", "기타")] += 1
            rows_md.append(
                f"| R-{rid:03d} | {md_escape(r.get('req_name'))} | {md_escape(r.get('req_detail'))} "
                f"| {md_escape(r.get('req_type'))} | {md_escape(r.get('strategy'))} | {md_escape(src)} |"
            )

    fm = {
        "project": slug,
        "title": title,
        "domain": domain,
        "doc_type": "requirements",
        "source_doc_count": len(docs),
        "req_count": rid,
    }
    lines = ["---"]
    lines.append(yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip())
    lines.append("---\n")
    lines.append(f"# {title} — 요구사항 정의\n")
    lines.append(f"- **도메인**: {domain}")
    lines.append(f"- **원본 문서**: {len(docs)}건 / **추출 요구사항**: {rid}건")
    if type_counter:
        dist = ", ".join(f"{k} {v}" for k, v in type_counter.most_common())
        lines.append(f"- **유형 분포**: {dist}")
    lines.append("\n## 원본 출처\n")
    for s in sorted(set(sources)):
        lines.append(f"- `{s}`")
    lines.append("\n## 요구사항\n")
    lines.append("| ID | 요구사항명 | 요구사항 | 유형구분 | 대응전략 | 출처 |")
    lines.append("|----|-----------|---------|---------|---------|------|")
    lines.extend(rows_md)
    lines.append("")
    return "\n".join(lines), rid, type_counter


def build_index(by_slug: dict[str, list[dict]], proj_stats: dict) -> str:
    total_reqs = sum(s["req_count"] for s in proj_stats.values())
    total_docs = sum(len(v) for v in by_slug.values())
    global_types: Counter = Counter()
    for s in proj_stats.values():
        global_types.update(s["types"])

    lines = ["---", "title: 요구사항 정의서 마스터 인덱스", "doc_type: requirements-index", "---\n"]
    lines.append("# 요구사항 정의서 마스터 인덱스\n")
    lines.append(
        f"26년치 프로젝트 요구사항 정의서에서 추출한 구조화 데이터의 전체 인덱스. "
        f"신규 AI 시스템 요구사항·대응전략 도출의 근거 데이터로 사용한다.\n"
    )
    lines.append(f"- **프로젝트**: {len(proj_stats)}개")
    lines.append(f"- **원본 문서**: {total_docs}건")
    lines.append(f"- **추출 요구사항**: {total_reqs}건\n")

    lines.append("## 유형구분 분포 (전체)\n")
    lines.append("| 유형구분 | 건수 |")
    lines.append("|---------|------|")
    for k, v in global_types.most_common():
        lines.append(f"| {k} | {v} |")
    lines.append("")

    lines.append("## 프로젝트별 요약\n")
    lines.append("| 프로젝트 | 도메인 | 요구사항 수 | 주요 유형 | 문서 |")
    lines.append("|---------|--------|-----------|----------|------|")
    for slug in sorted(proj_stats, key=lambda s: -proj_stats[s]["req_count"]):
        s = proj_stats[slug]
        top = ", ".join(f"{k}({v})" for k, v in s["types"].most_common(3))
        lines.append(
            f"| {s['title']} | {s['domain']} | {s['req_count']} | {top} | [{slug}](./{slug}.md) |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    by_slug = load_extractions()
    if not by_slug:
        print("[WARN] _extracted/ 비어있음 — 먼저 extract_requirements.py 실행 필요")
        return 1

    proj_stats: dict = {}
    for slug, docs in by_slug.items():
        content, rid, types = build_project_doc(slug, docs)
        (DOCS_REQ / f"{slug}.md").write_text(content, encoding="utf-8")
        proj_stats[slug] = {
            "title": docs[0]["project_title"],
            "domain": docs[0].get("domain", "etc"),
            "req_count": rid,
            "types": types,
        }
        print(f"  ✓ {slug}.md ({rid}건)")

    (DOCS_REQ / "_index.md").write_text(build_index(by_slug, proj_stats), encoding="utf-8")
    print(f"[DONE] {len(proj_stats)} 프로젝트 문서 + _index.md 생성")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
