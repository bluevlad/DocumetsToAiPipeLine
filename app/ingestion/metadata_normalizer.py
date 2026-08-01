"""메타데이터 정규화.

프로젝트명, 연도, 문서 카테고리 등을 표준화.
"""

import re
from datetime import datetime
from pathlib import Path

from app.core.config import settings

# 연도 추출 패턴
_YEAR_PATTERN = re.compile(r"((?:19|20)\d{2})")

# 문서 카테고리 키워드 매핑 (한국어)
_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "제안서": ["제안서", "제안", "proposal", "RFP"],
    "설계서": ["설계서", "설계", "design", "아키텍처", "architecture"],
    "보고서": ["보고서", "보고", "report", "결과보고", "중간보고", "최종보고"],
    "소스코드": ["소스", "source", "src", "코드", "code", "개발"],
    "매뉴얼": ["매뉴얼", "manual", "가이드", "guide", "사용법", "운영"],
    "회의록": ["회의록", "회의", "meeting", "minutes", "협의"],
    "시험": ["시험", "테스트", "test", "검수", "검증", "QA"],
    "계약": ["계약", "contract", "계약서", "견적", "발주"],
    "교육": ["교육", "training", "학습", "과정"],
}


def _normalize_project_name(name: str) -> str:
    """프로젝트명 정규화: 앞뒤 공백/특수문자 정리."""
    # 앞뒤 공백, 언더스코어, 대시 제거
    name = name.strip().strip("_-")
    # 연속 공백 제거
    name = re.sub(r"\s+", " ", name)
    return name


def _extract_year(path_parts: tuple[str, ...], file_path: Path) -> str:
    """폴더명에서 연도 추출, 없으면 파일 수정일 폴백."""
    # 폴더명에서 연도 찾기 (첫 번째 매칭)
    for part in path_parts:
        match = _YEAR_PATTERN.search(part)
        if match:
            year = int(match.group(1))
            if 1990 <= year <= 2030:
                return str(year)

    # 폴백: 파일 수정일
    try:
        mtime = file_path.stat().st_mtime
        return str(datetime.fromtimestamp(mtime).year)
    except OSError:
        return "unknown"


def _classify_category(path_parts: tuple[str, ...], file_name: str) -> str:
    """경로/파일명 기반 문서 카테고리 분류."""
    search_text = " ".join(path_parts).lower() + " " + file_name.lower()

    for category, keywords in _CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in search_text:
                return category

    return "기타"


class MetadataNormalizer:
    """파일 경로에서 정규화된 메타데이터 추출."""

    def __init__(self, documents_root: str = settings.DOCUMENTS_ROOT):
        self.documents_root = Path(documents_root)

    def normalize(self, file_path: Path) -> dict:
        """파일 경로에서 정규화된 메타데이터 반환."""
        try:
            rel = file_path.relative_to(self.documents_root)
            parts = rel.parts
        except ValueError:
            parts = file_path.parts

        project_name = _normalize_project_name(parts[0]) if parts else "unknown"
        year = _extract_year(parts, file_path)
        category = _classify_category(parts, file_path.name)

        try:
            file_size = file_path.stat().st_size
        except OSError:
            file_size = 0

        return {
            "source_path": str(file_path),
            "file_name": file_path.name,
            "file_type": file_path.suffix.lower(),
            "file_size": file_size,
            "project": project_name,
            "sub_path": "/".join(parts[1:-1]) if len(parts) > 1 else "",
            "year": year,
            "category": category,
        }
