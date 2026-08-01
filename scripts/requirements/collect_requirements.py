"""Phase 0 — 요구사항 정의서 수집기.

문서 소스 루트 하위를 스캔하여 '요구사항 정의서' 계열 문서만 골라
`docs/requirements/_manifest.csv` 를 생성한다. (사람이 1회 검수하는 입력 목록)

매칭 규칙
  포함: 파일명에 '요구사항' 이 있고, (정의|분석|리스트|목록) 중 하나 포함
  제외: 작성법 / 양식 / 표준 / 질의서 / 결과서 / 설명서 / 샘플 / 임시(~$)

프로젝트 키 결정
  - 최상위 폴더가 `YYYY년` (연도 버킷)이면 바로 아래 `(기간) 이름` 하위폴더를
    실제 프로젝트로 보고 거기서 slug/title 도출
  - 그 외에는 _slugs.yaml 의 raw_name → slug 매핑 사용

Usage:
  .venv/bin/python scripts/requirements/collect_requirements.py \
      --source "/path/to/documents"
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

import yaml

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]
DOCS_REQ = ROOT / "docs" / "requirements"
SLUGS_FILE = ROOT / "docs" / "projects" / "_slugs.yaml"

DEFAULT_SOURCE = Path("./data/documents")

TRACKED_EXT = {".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".hwp", ".hwpx", ".pdf", ".txt"}

# 실제 '요구사항정의서' 본문 문서로 인정하는 핵심 토큰 (공백 변형 포함)
INCLUDE_CORE = (
    "요구사항정의", "요구사항 정의",
    "요구사항분석", "요구사항 분석",
    "요구사항리스트", "요구사항 리스트",
    "요구사항목록", "요구사항 목록",
)
# 요구사항정의서를 '대상으로만' 하는 래퍼 문서 / 양식 / 임시 → 제외
EXCLUDE = (
    "작성법", "작성방법", "양식", "템플릿", "표준",
    "질의서", "결과서", "설명서", "샘플",
    "내부검토", "검토계획", "검토준비", "검토팀", "검토결과",
    "계획서", "준비서", "점검", "체크", "회의록", "예시",
)
# 양식/템플릿/표준 폴더 아래 문서도 제외
EXCLUDE_PATH_PARTS = ("양식", "템플릿", "표준", "샘플")

PERIOD_PATTERN = re.compile(r"^\((\d{4})\.(\d{1,2})\s*-\s*(\d{4})\.(\d{1,2})\)\s*(.+)$")
YEARLY_PATTERN = re.compile(r"^(\d{4})년")


def load_slug_map() -> dict[str, dict]:
    data = yaml.safe_load(SLUGS_FILE.read_text(encoding="utf-8"))
    out = {}
    for slug, meta in data["projects"].items():
        out[meta["raw_name"]] = {"slug": slug, **meta}
    return out


def slugify(name: str) -> str:
    """한글 프로젝트명 → 보조 slug (연도 버킷 내부 하위 프로젝트용)."""
    name = re.sub(r"[\s_]+", "-", name.strip())
    name = re.sub(r"[^0-9A-Za-z가-힣\-]", "", name)
    return name.strip("-").lower() or "unknown"


def is_requirement_doc(rel_parts: tuple[str, ...]) -> bool:
    name = rel_parts[-1]
    if name.startswith("~$"):
        return False
    if "요구사항" not in name:
        return False
    if any(x in name for x in EXCLUDE):
        return False
    # 양식/템플릿/표준/샘플 폴더 하위 제외
    if any(p in part for part in rel_parts[:-1] for p in EXCLUDE_PATH_PARTS):
        return False
    return any(x in name for x in INCLUDE_CORE) or name.startswith("요구사항정의")


_VER_RE = re.compile(r"ver\.?\s*(\d+(?:\.\d+)*)\s*([a-z]?)", re.I)
_VNUM_RE = re.compile(r"[_\-\s]v(\d{2,})", re.I)
_DATE_RE = re.compile(r"(20\d{6}|\d{6})")


def doc_key(stem: str) -> str:
    """버전/날짜/중복 표식을 제거한 논리 문서 키."""
    s = stem.split("(")[0] if "(" in stem else stem
    s = _VER_RE.sub("", s)
    s = _VNUM_RE.sub("", s)
    s = _DATE_RE.sub("", s)
    s = re.sub(r"\[\d+\]", "", s)
    s = re.sub(r"[_\-\s.]+$", "", s)
    s = re.sub(r"\s+", " ", s).strip(" -_.")
    return s.lower() or stem.lower()


def version_score(stem: str, mtime: float) -> tuple:
    """정렬용 버전 점수: (ver tuple, date, mtime). 클수록 최신."""
    ver: tuple = (0,)
    m = _VER_RE.search(stem)
    if m:
        ver = tuple(int(x) for x in m.group(1).split("."))
        if m.group(2):
            ver = ver + (ord(m.group(2).lower()) - 96,)
    d = 0
    md = _DATE_RE.search(stem)
    if md:
        d = int(md.group(1))
    return (ver, d, mtime)


def resolve_project(rel_parts: tuple[str, ...], slug_map: dict) -> tuple[str, str]:
    """(slug, title) 반환."""
    top = rel_parts[0]
    meta = slug_map.get(top)
    # 1) 이름 기반 프로젝트(연도 버킷 아님)는 _slugs.yaml 매핑을 그대로 사용
    if meta and not meta.get("is_yearly"):
        return meta["slug"], meta.get("title", top)
    # 2) 연도 버킷(`YYYY년` 또는 is_yearly)이면 하위 `(기간) 이름` 을 실제 프로젝트로
    if (meta and meta.get("is_yearly")) or YEARLY_PATTERN.match(top):
        if len(rel_parts) < 2:
            return slugify(top), top
        sub = rel_parts[1]
        m = PERIOD_PATTERN.match(sub)
        if m:
            year = m.group(1)
            title = m.group(5).strip()
            return f"{year}-{slugify(title)}", title
        return f"{slugify(top)}-{slugify(sub)}", sub
    return slugify(top), top


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    ap.add_argument("--out", type=Path, default=DOCS_REQ / "_manifest.csv")
    args = ap.parse_args()

    source: Path = args.source
    if not source.exists():
        print(f"[ERROR] source not found: {source}", file=sys.stderr)
        return 1

    slug_map = load_slug_map()
    rows = []
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in TRACKED_EXT:
            continue
        rel = path.relative_to(source)
        if not is_requirement_doc(rel.parts):
            continue
        slug, title = resolve_project(rel.parts, slug_map)
        st = path.stat()
        stem = path.stem
        rows.append({
            "project_slug": slug,
            "project_title": title,
            "file_name": path.name,
            "ext": path.suffix.lower().lstrip("."),
            "size": st.st_size,
            "doc_key": doc_key(stem),
            "is_primary": "0",
            "source_rel": str(rel),
            "abs_path": str(path),
            "_score": version_score(stem, st.st_mtime),
        })

    # 논리 문서(project_slug + doc_key) 단위로 최신/최대 1건만 primary 지정
    best: dict[tuple, dict] = {}
    for r in rows:
        k = (r["project_slug"], r["doc_key"])
        cur = best.get(k)
        if cur is None or (r["_score"], r["size"]) > (cur["_score"], cur["size"]):
            best[k] = r
    for r in best.values():
        r["is_primary"] = "1"
    for r in rows:
        r.pop("_score", None)

    rows.sort(key=lambda r: (r["project_slug"], r["doc_key"], r["source_rel"]))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    n_proj = len({r["project_slug"] for r in rows})
    print(f"[OK] {len(rows)} files / {n_proj} projects → {args.out}")
    by_ext: dict[str, int] = {}
    for r in rows:
        by_ext[r["ext"]] = by_ext.get(r["ext"], 0) + 1
    print("ext:", dict(sorted(by_ext.items(), key=lambda x: -x[1])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
