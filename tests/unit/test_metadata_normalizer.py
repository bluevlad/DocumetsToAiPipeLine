"""metadata_normalizer 단위 테스트."""

import tempfile
from pathlib import Path

from app.ingestion.metadata_normalizer import (
    MetadataNormalizer,
    _classify_category,
    _extract_year,
    _normalize_project_name,
)


class TestNormalizeProjectName:
    def test_strip_whitespace(self):
        assert _normalize_project_name("  프로젝트A  ") == "프로젝트A"

    def test_strip_special(self):
        assert _normalize_project_name("__프로젝트-") == "프로젝트"

    def test_collapse_spaces(self):
        assert _normalize_project_name("프로젝트   A") == "프로젝트 A"


class TestExtractYear:
    def test_from_folder_name(self):
        parts = ("2015_웹개발", "설계서")
        assert _extract_year(parts, Path("/tmp/test.txt")) == "2015"

    def test_four_digit_year(self):
        parts = ("프로젝트2023", "docs")
        assert _extract_year(parts, Path("/tmp/test.txt")) == "2023"

    def test_fallback_to_mtime(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"test")
            path = Path(f.name)
        year = _extract_year(("noYear",), path)
        assert year.isdigit()
        path.unlink()


class TestClassifyCategory:
    def test_proposal(self):
        assert _classify_category(("프로젝트", "제안서"), "제안서_v1.hwp") == "제안서"

    def test_design(self):
        assert _classify_category(("프로젝트", "설계"), "상세설계서.doc") == "설계서"

    def test_report(self):
        assert _classify_category(("프로젝트",), "최종보고서.pptx") == "보고서"

    def test_source_code(self):
        assert _classify_category(("프로젝트", "소스코드"), "main.py") == "소스코드"

    def test_meeting(self):
        assert _classify_category(("프로젝트",), "회의록_0301.docx") == "회의록"

    def test_unknown(self):
        assert _classify_category(("misc",), "random.txt") == "기타"


class TestMetadataNormalizer:
    def test_normalize_returns_all_fields(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"test content")
            path = Path(f.name)

        normalizer = MetadataNormalizer(documents_root=str(path.parent))
        meta = normalizer.normalize(path)

        assert "source_path" in meta
        assert "file_name" in meta
        assert "file_type" in meta
        assert "file_size" in meta
        assert "project" in meta
        assert "year" in meta
        assert "category" in meta
        assert meta["file_type"] == ".txt"

        path.unlink()
