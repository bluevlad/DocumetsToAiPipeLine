"""텍스트 파일 변환기.

TXT (5,235개), SQL (2,556개) 등 순수 텍스트 파일 처리.
"""

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# 시도할 인코딩 순서
ENCODINGS = ["utf-8", "cp949", "euc-kr", "utf-16", "latin-1"]


class TextConverter:
    """텍스트 파일 읽기."""

    SUPPORTED_EXTENSIONS = {".txt", ".sql", ".md", ".csv", ".log"}

    def can_handle(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS

    async def convert(self, file_path: Path) -> str:
        """텍스트 파일 읽기. 인코딩 자동 감지."""
        try:
            return await asyncio.to_thread(self._read_text, file_path)
        except Exception as e:
            logger.warning("Text read failed for %s: %s", file_path, e)
            return ""

    def _read_text(self, file_path: Path) -> str:
        """여러 인코딩을 시도하여 텍스트 읽기."""
        for encoding in ENCODINGS:
            try:
                return file_path.read_text(encoding=encoding)
            except (UnicodeDecodeError, UnicodeError):
                continue
        return file_path.read_text(encoding="utf-8", errors="replace")
