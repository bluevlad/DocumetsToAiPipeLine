"""변환기 단독 테스트 스크립트.

임베딩/벡터DB 없이 문서 변환 + 청킹만 테스트.
사용법: python scripts/test_converters.py [max_files]
"""

import asyncio
import sys
from collections import Counter
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings
from app.ingestion.converters import HwpConverter, OfficeConverter, PdfConverter, TextConverter
from app.ingestion.chunker import DocumentChunker


TARGET_EXTENSIONS = {
    ".hwp", ".doc", ".docx", ".ppt", ".pptx",
    ".xls", ".xlsx", ".pdf", ".txt", ".sql",
}


async def test_single_file(file_path: Path, converters: list, chunker: DocumentChunker) -> dict:
    """단일 파일 변환 테스트."""
    converter = None
    for c in converters:
        if c.can_handle(file_path):
            converter = c
            break

    if not converter:
        return {"status": "skipped", "type": file_path.suffix}

    try:
        text = await converter.convert(file_path)
        if not text or len(text.strip()) < 10:
            return {"status": "empty", "type": file_path.suffix}

        chunks = chunker.chunk(text, {"source_path": str(file_path)})
        return {
            "status": "success",
            "type": file_path.suffix,
            "text_len": len(text),
            "chunks": len(chunks),
            "preview": text[:200].replace("\n", " "),
        }
    except Exception as e:
        return {"status": "error", "type": file_path.suffix, "error": str(e)}


async def main():
    max_files = int(sys.argv[1]) if len(sys.argv) > 1 else 100

    converters = [HwpConverter(), OfficeConverter(), PdfConverter(), TextConverter()]
    chunker = DocumentChunker()

    root = Path(settings.DOCUMENTS_ROOT)
    print(f"문서 소스: {root}")
    print(f"테스트 대상: 최대 {max_files}개 파일")
    print("=" * 60)

    # 파일 수집 (다양한 확장자를 골고루)
    files_by_ext: dict[str, list[Path]] = {}
    for f in root.rglob("*"):
        if f.is_file() and f.suffix.lower() in TARGET_EXTENSIONS:
            ext = f.suffix.lower()
            if ext not in files_by_ext:
                files_by_ext[ext] = []
            files_by_ext[ext].append(f)

    # 확장자별로 균등 샘플링
    selected = []
    per_ext = max(1, max_files // len(files_by_ext)) if files_by_ext else 0
    for ext, file_list in sorted(files_by_ext.items()):
        sample = file_list[:per_ext]
        selected.extend(sample)
        print(f"  {ext}: {len(sample)}개 선택 (전체 {len(file_list)}개)")

    selected = selected[:max_files]
    print(f"\n총 {len(selected)}개 파일 테스트 시작...\n")

    # 변환 테스트
    results = Counter()
    type_results: dict[str, Counter] = {}
    sample_outputs = []

    for i, file_path in enumerate(selected, 1):
        result = await test_single_file(file_path, converters, chunker)
        status = result["status"]
        ext = result["type"]

        results[status] += 1
        if ext not in type_results:
            type_results[ext] = Counter()
        type_results[ext][status] += 1

        if status == "success" and len(sample_outputs) < 5:
            sample_outputs.append(result)

        marker = {"success": "OK", "error": "ER", "empty": "--", "skipped": "SK"}
        print(f"  [{i:3d}/{len(selected)}] {marker.get(status, '??')} {ext:6s} {file_path.name[:50]}")

    # 결과 요약
    print("\n" + "=" * 60)
    print("결과 요약:")
    for status, count in sorted(results.items()):
        print(f"  {status}: {count}")

    print(f"\n확장자별 성공률:")
    for ext in sorted(type_results.keys()):
        ext_counts = type_results[ext]
        total = sum(ext_counts.values())
        success = ext_counts.get("success", 0)
        print(f"  {ext}: {success}/{total} ({success / max(total, 1) * 100:.0f}%)")

    if sample_outputs:
        print(f"\nSample outputs ({len(sample_outputs)}):")
        for s in sample_outputs:
            preview = s['preview'][:150].encode('ascii', errors='replace').decode('ascii')
            print(f"\n  --- [{s['type']}] {s['text_len']} chars -> {s['chunks']} chunks ---")
            print(f"  {preview}...")


if __name__ == "__main__":
    asyncio.run(main())
