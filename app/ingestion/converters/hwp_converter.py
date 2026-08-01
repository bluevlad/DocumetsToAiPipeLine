"""HWP 문서 변환기.

38,597개 HWP 파일 처리를 위한 핵심 컨버터.
전략: olefile 직접 파싱 우선 → 실패 시 LibreOffice CLI 폴백.

HWP5 포맷은 OLE2 컨테이너 기반으로, 내부에 BodyText 스트림이 있음.
텍스트는 zlib 압축된 바이너리 레코드로 저장됨.
"""

import asyncio
import logging
import struct
import zlib
from pathlib import Path

import olefile

logger = logging.getLogger(__name__)


class HwpConverter:
    """HWP 파일을 텍스트로 변환."""

    SUPPORTED_EXTENSIONS = {".hwp"}

    def can_handle(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS

    async def convert(self, file_path: Path) -> str:
        """HWP 파일을 텍스트로 변환.

        1차: olefile 직접 파싱 (HWP5 바이너리)
        2차: LibreOffice CLI 폴백
        """
        text = await self._try_olefile(file_path)
        if not text:
            text = await self._try_libreoffice(file_path)
        return text or ""

    async def _try_olefile(self, file_path: Path) -> str | None:
        """olefile을 이용한 HWP5 직접 파싱."""
        try:
            return await asyncio.to_thread(self._parse_hwp5, file_path)
        except Exception as e:
            logger.debug("olefile parsing failed for %s: %s", file_path, e)
            return None

    def _parse_hwp5(self, file_path: Path) -> str | None:
        """HWP5 바이너리 포맷 파싱 (동기)."""
        if not olefile.isOleFile(str(file_path)):
            return None

        ole = olefile.OleFileIO(str(file_path))
        try:
            # FileHeader에서 압축 여부 확인
            header = ole.openstream("FileHeader").read()
            is_compressed = bool(header[36] & 1)

            # BodyText 섹션에서 텍스트 추출
            text_parts = []
            section_idx = 0
            while True:
                stream_name = f"BodyText/Section{section_idx}"
                if not ole.exists(stream_name):
                    break

                data = ole.openstream(stream_name).read()
                if is_compressed:
                    try:
                        data = zlib.decompress(data, -15)
                    except zlib.error:
                        section_idx += 1
                        continue

                section_text = self._extract_text_from_records(data)
                if section_text:
                    text_parts.append(section_text)
                section_idx += 1

            return "\n".join(text_parts) if text_parts else None
        finally:
            ole.close()

    def _extract_text_from_records(self, data: bytes) -> str:
        """HWP 바이너리 레코드에서 텍스트 추출."""
        text_parts = []
        pos = 0

        while pos < len(data) - 4:
            try:
                # 레코드 헤더: 4바이트 (tag_id, level, size)
                header = struct.unpack_from("<I", data, pos)[0]
                tag_id = header & 0x3FF
                size = (header >> 20) & 0xFFF

                if size == 0xFFF:
                    if pos + 8 > len(data):
                        break
                    size = struct.unpack_from("<I", data, pos + 4)[0]
                    pos += 8
                else:
                    pos += 4

                if pos + size > len(data):
                    break

                # HWPTAG_PARA_TEXT (tag_id == 67)
                if tag_id == 67:
                    record_data = data[pos : pos + size]
                    text = self._decode_para_text(record_data)
                    if text.strip():
                        text_parts.append(text)

                pos += size
            except (struct.error, IndexError):
                break

        return "\n".join(text_parts)

    def _decode_para_text(self, data: bytes) -> str:
        """HWPTAG_PARA_TEXT 레코드에서 UTF-16LE 텍스트 디코딩."""
        chars = []
        i = 0
        while i < len(data) - 1:
            code = struct.unpack_from("<H", data, i)[0]
            i += 2

            if code == 0:
                break

            # HWP 특수 컨트롤 코드 건너뛰기
            if code < 32:
                # 인라인 컨트롤: 추가 바이트 건너뛰기
                skip_map = {
                    1: 0, 2: 0, 3: 0, 4: 0,   # 기본 컨트롤
                    5: 0, 6: 0, 7: 0, 8: 0,
                    9: 6, 10: 14, 11: 14,       # 탭, 필드, 그리기 객체
                    12: 0, 13: 0, 14: 0, 15: 14,
                    16: 14, 17: 14, 18: 14, 19: 14,
                    20: 14, 21: 14, 22: 14, 23: 14,
                    24: 0, 25: 0, 26: 0, 27: 0,
                    28: 0, 29: 0, 30: 14, 31: 14,
                }
                skip = skip_map.get(code, 0)
                i += skip

                # 줄바꿈 처리
                if code == 13:
                    chars.append("\n")
                elif code == 9:
                    chars.append("\t")
                continue

            chars.append(chr(code))

        return "".join(chars)

    async def _try_libreoffice(self, file_path: Path) -> str | None:
        """LibreOffice CLI를 이용한 HWP 변환 폴백."""
        import tempfile

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                proc = await asyncio.create_subprocess_exec(
                    "soffice",
                    "--headless",
                    "--convert-to", "txt:Text",
                    "--outdir", tmpdir,
                    str(file_path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await asyncio.wait_for(proc.communicate(), timeout=30)

                txt_file = Path(tmpdir) / (file_path.stem + ".txt")
                if txt_file.exists():
                    return txt_file.read_text(encoding="utf-8", errors="replace")
        except (FileNotFoundError, asyncio.TimeoutError) as e:
            logger.debug("LibreOffice fallback failed for %s: %s", file_path, e)
        return None
