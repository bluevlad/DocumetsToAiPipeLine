"""프로젝트 폴더 메타데이터 문서 자동 생성기.

문서 소스 루트(SOURCE_ROOT) 하위 각 폴더를 스캔하여 `docs/projects/<slug>/index.md`
스켈레톤을 만들고, 재실행 시에는 frontmatter의 `file_count`·`formats`만 갱신한다
(본문과 사용자가 채운 메타데이터는 보존).

Usage:
  py scripts/generate_project_docs.py --scan
      → 폴더 목록 + slug 후보를 stdout 표로 출력 (매핑 테이블 작성 참고용)

  py scripts/generate_project_docs.py --scan --emit-slugs
      → docs/projects/_slugs.yaml 초안 생성 (이미 있으면 덮지 않음)

  py scripts/generate_project_docs.py --generate --all
      → _slugs.yaml에 정의된 모든 프로젝트의 index.md 생성/갱신

  py scripts/generate_project_docs.py --generate --slug <slug>
      → 단일 프로젝트만 생성/갱신

  py scripts/generate_project_docs.py --update-stats
      → 기존 index.md의 file_count·formats만 재집계

  py scripts/generate_project_docs.py --update-index
      → docs/projects/by-year.md 연도별 인덱스 생성/갱신
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter

# Windows 콘솔 한글 출력 (cp949 → utf-8)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
SOURCE_ROOT = Path("./data/documents")
DOCS_ROOT = ROOT / "docs" / "projects"
SLUGS_FILE = DOCS_ROOT / "_slugs.yaml"

# 통계 집계 대상 확장자
TRACKED_EXTENSIONS = {
    ".hwp", ".hwpx", ".doc", ".docx", ".ppt", ".pptx",
    ".xls", ".xlsx", ".pdf", ".txt", ".md",
}

# `(YYYY.MM - YYYY.MM) 이름` 패턴
PERIOD_PATTERN = re.compile(
    r"^\((\d{4})\.(\d{1,2})\s*-\s*(\d{4})\.(\d{1,2})\)\s*(.+)$"
)
# `YYYY년` 패턴
YEARLY_PATTERN = re.compile(r"^(\d{4})년$")


@dataclass
class FolderScan:
    """단일 프로젝트 폴더 스캔 결과."""

    raw_name: str
    abs_path: Path
    period_start: str | None = None  # "YYYY-MM"
    period_end: str | None = None
    title: str = ""
    is_yearly: bool = False
    yearly: str | None = None  # "1999"
    file_count: int = 0
    formats: dict[str, int] = field(default_factory=dict)

    @property
    def auto_slug(self) -> str:
        """원본 이름에서 자동 생성한 영문 slug 후보 (사람 검토 필요)."""
        if self.is_yearly:
            return f"yearly-{self.yearly}"
        base = self.title or self.raw_name
        # ASCII 영숫자/공백/하이픈만 남기고 나머지 제거
        s = re.sub(r"[^\w\s-]", "", base, flags=re.ASCII)
        s = re.sub(r"\s+", "-", s.strip()).lower()
        if self.period_start:
            return f"{self.period_start[:4]}-{s}" if s else self.period_start[:4]
        return s or "untitled"


def parse_folder_name(name: str) -> tuple[str | None, str | None, str, bool, str | None]:
    """폴더명 → (period_start, period_end, title, is_yearly, yearly)."""
    if m := PERIOD_PATTERN.match(name):
        sy, sm, ey, em, title = m.groups()
        return f"{sy}-{int(sm):02d}", f"{ey}-{int(em):02d}", title.strip(), False, None
    if m := YEARLY_PATTERN.match(name):
        year = m.group(1)
        return None, None, name, True, year
    return None, None, name, False, None


def count_files(folder: Path) -> tuple[int, dict[str, int]]:
    """폴더 재귀 스캔 → (총 파일 수, 확장자별 카운트)."""
    counter: Counter[str] = Counter()
    total = 0
    try:
        for p in folder.rglob("*"):
            if not p.is_file():
                continue
            total += 1
            ext = p.suffix.lower()
            if ext in TRACKED_EXTENSIONS:
                counter[ext.lstrip(".")] += 1
    except (OSError, PermissionError) as e:
        print(f"[warn] {folder}: {e}", file=sys.stderr)
    return total, dict(sorted(counter.items()))


def scan_all() -> list[FolderScan]:
    """SOURCE_ROOT 직속 폴더 전체 스캔."""
    if not SOURCE_ROOT.exists():
        sys.exit(f"[error] source root not found: {SOURCE_ROOT}")
    results: list[FolderScan] = []
    for entry in sorted(SOURCE_ROOT.iterdir()):
        if not entry.is_dir():
            continue
        ps, pe, title, is_yearly, yearly = parse_folder_name(entry.name)
        results.append(FolderScan(
            raw_name=entry.name,
            abs_path=entry,
            period_start=ps,
            period_end=pe,
            title=title,
            is_yearly=is_yearly,
            yearly=yearly,
        ))
    return results


def load_slugs() -> dict[str, dict[str, Any]]:
    """_slugs.yaml 로드. 없으면 빈 dict."""
    if not SLUGS_FILE.exists():
        return {}
    with SLUGS_FILE.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("projects", {})


def emit_slugs_skeleton(scans: list[FolderScan]) -> None:
    """_slugs.yaml 초안 작성 (이미 존재하면 중단)."""
    if SLUGS_FILE.exists():
        sys.exit(f"[error] {SLUGS_FILE} already exists — refusing to overwrite")
    payload: dict[str, Any] = {
        "version": 1,
        "source_root": str(SOURCE_ROOT).replace("\\", "/"),
        "projects": {},
    }
    for s in scans:
        payload["projects"][s.auto_slug] = {
            "raw_name": s.raw_name,
            "title": s.title or s.raw_name,
            "period_start": s.period_start,
            "period_end": s.period_end,
            "is_yearly": s.is_yearly,
            "domain": "etc",
            "msp_potential": "low",
        }
    SLUGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with SLUGS_FILE.open("w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, allow_unicode=True, sort_keys=False)
    print(f"[ok] wrote skeleton: {SLUGS_FILE} ({len(scans)} entries)")


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """md 텍스트 → (frontmatter dict, body)."""
    if not text.startswith("---\n"):
        return {}, text
    try:
        _, fm, body = text.split("---\n", 2)
    except ValueError:
        return {}, text
    return yaml.safe_load(fm) or {}, body


def render_md(fm: dict[str, Any], body: str) -> str:
    """frontmatter + body → md 텍스트."""
    fm_text = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{fm_text}\n---\n{body}"


def default_body(title: str) -> str:
    return f"""
## 개요

<1-2줄 요약: 무엇을 했고 누구에게 제공했는가>

## 핵심 산출물

-

## 사용 기술 / 아키텍처

-

## MSP 전환 관점 메모

- **재사용 가능 모듈**:
- **도메인 해자**:
- **규제 / 인증 요구**:
- **현재 시장 적합성**:

## 주요 파일 (샘플)

-
"""


def generate_one(slug: str, meta: dict[str, Any]) -> None:
    """단일 프로젝트의 index.md 생성/갱신."""
    raw_name = meta.get("raw_name")
    if not raw_name:
        print(f"[skip] {slug}: raw_name missing")
        return
    src = SOURCE_ROOT / raw_name
    if not src.exists():
        print(f"[skip] {slug}: source folder not found ({src})")
        return

    is_yearly = meta.get("is_yearly", False)
    if is_yearly:
        out_path = DOCS_ROOT / "yearly" / f"{meta.get('period_start', slug)[:4]}.md"
    else:
        out_path = DOCS_ROOT / slug / "index.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    file_count, formats = count_files(src)

    if out_path.exists():
        existing = out_path.read_text(encoding="utf-8")
        fm, body = split_frontmatter(existing)
    else:
        fm, body = {}, default_body(meta.get("title", slug))

    # 자동 채움 필드 (사용자 수정 금지)
    fm["id"] = slug
    fm.setdefault("title", meta.get("title", slug))
    if meta.get("period_start"):
        fm.setdefault("period_start", meta["period_start"])
    if meta.get("period_end"):
        fm.setdefault("period_end", meta["period_end"])
    fm.setdefault("client", meta.get("client", ""))
    fm.setdefault("domain", meta.get("domain", "etc"))
    fm.setdefault("tech_stack", [])
    fm.setdefault("status", "completed")
    fm["source_path"] = str(src).replace("\\", "/")
    fm["file_count"] = file_count
    fm["formats"] = formats
    fm.setdefault("msp_potential", meta.get("msp_potential", "low"))
    fm.setdefault("tags", [])

    out_path.write_text(render_md(fm, body), encoding="utf-8")
    print(f"[ok] {slug}: {file_count} files → {out_path.relative_to(ROOT)}")


def cmd_scan(emit_slugs: bool) -> None:
    scans = scan_all()
    print(f"{'auto-slug':40s}  {'period':18s}  raw_name")
    print("-" * 100)
    for s in scans:
        period = f"{s.period_start or '-':>7s}~{s.period_end or '-':<7s}"
        print(f"{s.auto_slug:40s}  {period:18s}  {s.raw_name}")
    print(f"\n[summary] {len(scans)} folders")
    if emit_slugs:
        emit_slugs_skeleton(scans)


def cmd_generate(slug: str | None, all_: bool) -> None:
    projects = load_slugs()
    if not projects:
        sys.exit(f"[error] no projects in {SLUGS_FILE} — run --scan --emit-slugs first")
    if all_:
        for s, meta in projects.items():
            generate_one(s, meta)
    elif slug:
        if slug not in projects:
            sys.exit(f"[error] slug '{slug}' not in {SLUGS_FILE}")
        generate_one(slug, projects[slug])
    else:
        sys.exit("[error] specify --slug <slug> or --all")


def collect_frontmatters() -> list[dict[str, Any]]:
    """docs/projects 하위 모든 md의 frontmatter를 수집 (_template 제외)."""
    paths = [
        *DOCS_ROOT.glob("*/index.md"),
        *DOCS_ROOT.glob("yearly/*.md"),
    ]
    out: list[dict[str, Any]] = []
    for p in paths:
        fm, _ = split_frontmatter(p.read_text(encoding="utf-8"))
        if not fm:
            continue
        fm["_path"] = p.relative_to(DOCS_ROOT).as_posix()
        out.append(fm)
    return out


def _year_of(fm: dict[str, Any]) -> str:
    """frontmatter의 period_start에서 연도 추출. 없으면 'undated'."""
    ps = fm.get("period_start")
    if isinstance(ps, str) and len(ps) >= 4 and ps[:4].isdigit():
        return ps[:4]
    return "undated"


def _fmt_summary(formats: dict[str, int] | None) -> str:
    """formats dict → 'hwp:28 pdf:113 ...' 짧은 요약."""
    if not formats:
        return "-"
    top = sorted(formats.items(), key=lambda x: -x[1])[:3]
    return " ".join(f"{k}:{v}" for k, v in top)


def cmd_update_index() -> None:
    """docs/projects/by-year.md 생성 — 연도별 프로젝트 인덱스."""
    fms = collect_frontmatters()
    if not fms:
        sys.exit("[error] no frontmatters found — run --generate --all first")

    # 연도별 그룹핑
    by_year: dict[str, list[dict[str, Any]]] = {}
    for fm in fms:
        by_year.setdefault(_year_of(fm), []).append(fm)

    # 최신 연도부터 (undated는 맨 아래)
    sorted_years = sorted(
        (y for y in by_year if y != "undated"), reverse=True
    )
    if "undated" in by_year:
        sorted_years.append("undated")

    lines: list[str] = [
        "# Projects By Year",
        "",
        "`docs/projects/` 하위 모든 프로젝트를 **시작 연도별**로 그룹핑한 인덱스입니다.",
        f"`scripts/generate_project_docs.py --update-index`로 자동 갱신됩니다.",
        "",
        f"- 총 {len(fms)}건",
        f"- 총 파일 수: {sum(fm.get('file_count', 0) for fm in fms):,}",
        "",
    ]

    for year in sorted_years:
        items = sorted(
            by_year[year],
            key=lambda x: (x.get("period_start") or "9999", x.get("id", "")),
        )
        heading = "Undated" if year == "undated" else year
        lines.append(f"## {heading}  _({len(items)}건)_")
        lines.append("")
        lines.append("| Title | Period | Domain | MSP | Files | Formats | Link |")
        lines.append("|-------|--------|--------|-----|------:|---------|------|")
        for fm in items:
            period = fm.get("period_start") or "-"
            if fm.get("period_end"):
                period = f"{period} ~ {fm['period_end']}"
            lines.append(
                f"| {fm.get('title', '-')} "
                f"| {period} "
                f"| {fm.get('domain', '-')} "
                f"| {fm.get('msp_potential', '-')} "
                f"| {fm.get('file_count', 0):,} "
                f"| {_fmt_summary(fm.get('formats'))} "
                f"| [{fm.get('id', '-')}](./{fm['_path']}) |"
            )
        lines.append("")

    out_path = DOCS_ROOT / "by-year.md"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[ok] wrote {out_path.relative_to(ROOT)} ({len(fms)} entries, {len(sorted_years)} years)")


def cmd_update_stats() -> None:
    """기존 index.md의 file_count·formats만 갱신."""
    projects = load_slugs()
    for slug, meta in projects.items():
        is_yearly = meta.get("is_yearly", False)
        path = (DOCS_ROOT / "yearly" / f"{meta.get('period_start', slug)[:4]}.md"
                if is_yearly else DOCS_ROOT / slug / "index.md")
        if not path.exists():
            continue
        src = SOURCE_ROOT / meta["raw_name"]
        if not src.exists():
            continue
        fm, body = split_frontmatter(path.read_text(encoding="utf-8"))
        file_count, formats = count_files(src)
        fm["file_count"] = file_count
        fm["formats"] = formats
        path.write_text(render_md(fm, body), encoding="utf-8")
        print(f"[ok] {slug}: {file_count} files")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scan", action="store_true", help="폴더 목록·slug 후보 출력")
    ap.add_argument("--emit-slugs", action="store_true", help="--scan과 함께: _slugs.yaml 초안 생성")
    ap.add_argument("--generate", action="store_true", help="index.md 생성/갱신")
    ap.add_argument("--all", action="store_true", help="--generate와 함께: 전체 일괄 처리")
    ap.add_argument("--slug", type=str, help="--generate와 함께: 특정 slug만 처리")
    ap.add_argument("--update-stats", action="store_true", help="기존 md의 file_count·formats만 갱신")
    ap.add_argument("--update-index", action="store_true", help="docs/projects/by-year.md 연도별 인덱스 갱신")
    args = ap.parse_args()

    if args.scan:
        cmd_scan(emit_slugs=args.emit_slugs)
    elif args.generate:
        cmd_generate(slug=args.slug, all_=args.all)
    elif args.update_stats:
        cmd_update_stats()
    elif args.update_index:
        cmd_update_index()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
