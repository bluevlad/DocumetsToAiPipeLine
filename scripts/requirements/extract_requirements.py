"""Phase 2 — 요구사항 정의서 → 5필드 구조화 추출 (Claude).

각 primary 문서를 표 보존 텍스트로 변환한 뒤, Claude 로
  요구사항명 / 요구사항 / 유형구분 / 대응전략 / 출처
5필드를 추출하여 JSON 캐시에 저장한다. (재실행 시 캐시 건너뜀)

정책: 대응전략은 원문에 기재된 것만 추출. 없으면 "(원문 미기재)".

환경:
  ANTHROPIC_API_KEY 필요 (.env 또는 환경변수)

Usage:
  .venv/bin/python scripts/requirements/extract_requirements.py [--limit N] [--slug X]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.requirements.converter import convert_to_text  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DOCS_REQ = ROOT / "docs" / "requirements"
MANIFEST = DOCS_REQ / "_manifest.csv"
EXTRACTED_DIR = DOCS_REQ / "_extracted"
SCHEMA = yaml.safe_load((DOCS_REQ / "_schema.yaml").read_text(encoding="utf-8"))
SLUGS = yaml.safe_load((ROOT / "docs" / "projects" / "_slugs.yaml").read_text(encoding="utf-8"))

TYPE_ENUM = SCHEMA["type_enum"]
MAX_CHARS = 60_000

# ── 추출 프로바이더 ──────────────────────────────────────────
#   ollama(무료/로컬) | openai(gpt-4o-mini, 저비용) | anthropic(claude, 최상)
PROVIDER = os.environ.get("EXTRACT_PROVIDER", "ollama").lower()
ANTHROPIC_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-5-20250929")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OPENAI_MODEL = os.environ.get("EXTRACT_OPENAI_MODEL", "gpt-4o-mini")

SYSTEM_PROMPT = f"""너는 SI 프로젝트 산출물 분석 전문가다. 주어진 '요구사항 정의서' 원문 텍스트(표 포함)에서
개별 요구사항 항목을 추출해 구조화한다.

반드시 아래 규칙을 지켜라:
1. 표/목록의 각 요구사항 항목을 1건씩 추출한다. 표지·목차·서명란·빈 항목은 제외한다.
2. 각 항목을 다음 필드로 정리한다:
   - req_name   : 요구사항명 (짧은 제목, 원문 항목명 우선)
   - req_detail : 요구사항 상세 (원문 충실, 의미 보존하여 정리)
   - req_type   : 유형구분 — 반드시 다음 중 하나: {TYPE_ENUM}
   - strategy   : 대응전략/구현방안
   - source_loc : 원문 내 위치 식별자 (요구사항ID, 항목번호, 표/시트명 등). 없으면 "".

3. [유형구분 분류 기준] 항목마다 **개별적으로** 내용을 보고 판단한다. 한 문서를 한 유형으로 몰아넣지 마라.
   - 기능: 업무 처리, 화면, 조회/등록/수정, 계산, 출력 등 시스템이 해야 할 일 (대부분 여기 해당)
   - 비기능-성능: 응답시간/처리량/동시접속/속도
   - 비기능-보안: 로그인/인증/권한/암호화/접근통제
   - 비기능-규제: 법규/보존기간/감사/컴플라이언스
   - 비기능-가용성: 이중화/백업/복구/무중단
   - 데이터: 데이터 구조/마이그레이션/코드체계
   - 인터페이스: **타 시스템과의 연계/전송/API/EAI 일 때만**. 단순 업무기능은 기능으로 분류.
   - 운영관리: 운영/모니터링/배포/관리자 기능
   - 제약사항: 기술/일정/예산/환경 제약

4. [대응전략 규칙 — 매우 중요]
   - strategy 에는 "어떻게 구현/대응할지(방법, 해결책)"가 원문에 별도로 적혀 있을 때만 그 내용을 넣는다.
   - req_detail 과 같은 내용을 절대 복사하지 마라. (요구사항 설명 ≠ 대응전략)
   - 구현방법/해결책이 원문에 없으면 정확히 "(원문 미기재)" 라고만 적는다. 추정·창작 금지.

5. 요구사항이 전혀 없는 문서(양식/표지만 있음 등)는 빈 배열을 반환한다.
6. 출력은 JSON 객체 하나: {{"requirements": [ {{...}}, ... ]}} — 다른 텍스트 없이 JSON만."""


def load_env() -> None:
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def project_meta(slug: str) -> dict:
    p = SLUGS["projects"].get(slug, {})
    return {"domain": p.get("domain", "etc")}


def _call_ollama(system: str, user: str) -> str:
    import urllib.request

    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "format": "json",
        "stream": False,
        "options": {"temperature": 0, "num_ctx": 16384},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat", data=payload,
        headers={"Content-Type": "application/json"},
    )
    timeout = int(os.environ.get("OLLAMA_TIMEOUT", "300"))
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    return data["message"]["content"]


def _call_openai(client, system: str, user: str) -> str:
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp.choices[0].message.content


def _call_anthropic(client, system: str, user: str) -> str:
    msg = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=8000,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return msg.content[0].text


def extract_one(client, text: str, file_name: str) -> list[dict]:
    text = text[:MAX_CHARS]
    user = f"원본 파일명: {file_name}\n\n--- 요구사항 정의서 원문 ---\n{text}"
    if PROVIDER == "ollama":
        raw = _call_ollama(SYSTEM_PROMPT, user)
    elif PROVIDER == "openai":
        raw = _call_openai(client, SYSTEM_PROMPT, user)
    else:
        raw = _call_anthropic(client, SYSTEM_PROMPT, user)
    raw = raw.strip()
    # JSON 블록 추출
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        data = json.loads(raw[start:end + 1])
    reqs = data.get("requirements", [])
    # 유형 검증
    for r in reqs:
        if r.get("req_type") not in TYPE_ENUM:
            r["req_type"] = "기타"
    return reqs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--slug", default="")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    # .env 를 먼저 로드한 뒤 프로바이더/모델 설정을 확정 (import 시점 기본값 덮어쓰기)
    global PROVIDER, ANTHROPIC_MODEL, OLLAMA_MODEL, OLLAMA_URL, OPENAI_MODEL
    load_env()
    PROVIDER = os.environ.get("EXTRACT_PROVIDER", PROVIDER).lower()
    ANTHROPIC_MODEL = os.environ.get("LLM_MODEL", ANTHROPIC_MODEL)
    OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", OLLAMA_MODEL)
    OLLAMA_URL = os.environ.get("OLLAMA_URL", OLLAMA_URL)
    OPENAI_MODEL = os.environ.get("EXTRACT_OPENAI_MODEL", OPENAI_MODEL)

    client = None
    if PROVIDER == "ollama":
        print(f"[provider=ollama] model={OLLAMA_MODEL} @ {OLLAMA_URL} (무료/로컬)")
    elif PROVIDER == "openai":
        if not os.environ.get("OPENAI_API_KEY"):
            print("[ERROR] OPENAI_API_KEY 미설정", file=sys.stderr)
            return 2
        from openai import OpenAI
        client = OpenAI()
        print(f"[provider=openai] model={OPENAI_MODEL}")
    else:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("[ERROR] ANTHROPIC_API_KEY 미설정", file=sys.stderr)
            return 2
        from anthropic import Anthropic
        client = Anthropic()
        print(f"[provider=anthropic] model={ANTHROPIC_MODEL}")

    rows = [r for r in csv.DictReader(MANIFEST.open(encoding="utf-8")) if r["is_primary"] == "1"]
    if args.slug:
        rows = [r for r in rows if r["project_slug"] == args.slug]
    if args.limit:
        rows = rows[: args.limit]

    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    n_ok = n_skip = n_empty = n_fail = total_reqs = 0

    for i, r in enumerate(rows, 1):
        slug = r["project_slug"]
        cache = EXTRACTED_DIR / f"{slug}__{r['doc_key']}.json"
        tag = f"[{i}/{len(rows)}] {slug} / {r['file_name'][:50]}"
        if cache.exists() and not args.force:
            n_skip += 1
            continue

        text = convert_to_text(r["abs_path"])
        if not text or len(text.strip()) < 30:
            print(f"  ✗ 변환실패 {tag}")
            n_fail += 1
            cache.with_suffix(".fail.txt").write_text(text or "", encoding="utf-8")
            continue

        try:
            reqs = extract_one(client, text, r["file_name"])
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ 추출실패 {tag}: {e}")
            n_fail += 1
            continue

        out = {
            "project_slug": slug,
            "project_title": r["project_title"],
            "domain": project_meta(slug)["domain"],
            "source_file": r["file_name"],
            "source_rel": r["source_rel"],
            "requirements": reqs,
        }
        cache.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        total_reqs += len(reqs)
        if reqs:
            n_ok += 1
            print(f"  ✓ {len(reqs):3d}건 {tag}")
        else:
            n_empty += 1
            print(f"  - 0건 {tag}")

    print(f"\n[DONE] ok={n_ok} empty={n_empty} skip={n_skip} fail={n_fail} | 요구사항 {total_reqs}건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
