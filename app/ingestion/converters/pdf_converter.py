"""PDF 문서 변환기.

1,524개 PDF 파일 처리. PyMuPDF(fitz) 사용.
"""

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class PdfConverter:
    """PDF 파일을 텍스트로 변환."""

    SUPPORTED_EXTENSIONS = {".pdf"}

    def can_handle(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS

    async def convert(self, file_path: Path) -> str:
        """PDF 파일을 텍스트로 변환. PyMuPDF 사용."""
        try:
            return await asyncio.to_thread(self._extract_text, file_path)
        except Exception as e:
            logger.warning("PDF conversion failed for %s: %s", file_path, e)
            return ""

    def _extract_text(self, file_path: Path) -> str:
        """PyMuPDF로 PDF 텍스트 추출 (동기)."""
        import fitz  # PyMuPDF

        doc = fitz.open(str(file_path))
        try:
            parts = []
            for page_num, page in enumerate(doc, 1):
                text = page.get_text().strip()
                if text:
                    parts.append(f"[Page {page_num}]\n{text}")
            return "\n\n".join(parts)
        finally:
            doc.close()
