"""실패 파일 확인 스크립트."""
import asyncio
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ingestion.progress_db import ProgressDB


async def main():
    db = ProgressDB()
    await db.initialize()
    try:
        async with db.db.execute(
            "SELECT file_path, error_msg FROM processed_files WHERE status='failed'"
        ) as cur:
            rows = await cur.fetchall()

        print(f"Total failed: {len(rows)}\n")

        # 에러 유형별 집계
        error_types = Counter()
        for r in rows:
            err = r[1] or "unknown"
            # 에러 유형 추출 (첫 번째 의미 있는 부분)
            if "empty or too short" in err:
                error_types["empty or too short"] += 1
            elif "unsupported format" in err:
                error_types["unsupported format"] += 1
            elif "encoding" in err.lower() or "codec" in err.lower():
                error_types["encoding error"] += 1
            elif "embedding" in err.lower():
                error_types["embedding error"] += 1
            elif "store" in err.lower():
                error_types["store error"] += 1
            elif "conversion" in err.lower() or "convert" in err.lower():
                error_types["conversion error"] += 1
            else:
                # 앞 60자 사용
                key = err[:60]
                error_types[key] += 1

        print("Error breakdown:")
        for err_type, count in error_types.most_common():
            print(f"  {err_type}: {count}")

        # 확장자별 집계
        ext_counts = Counter()
        for r in rows:
            ext = Path(r[0]).suffix.lower()
            ext_counts[ext] += 1

        print(f"\nBy extension:")
        for ext, count in ext_counts.most_common():
            print(f"  {ext}: {count}")

    finally:
        await db.close()


asyncio.run(main())
