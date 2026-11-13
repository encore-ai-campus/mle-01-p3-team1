"""Idempotent download + offline-load verification for Hybrid Cross-Encoder.

Run once after `uv sync`, before serving retrieval requests:
    uv run --no-sync python -m src.hybrid.prepare_models

Subsequent runs skip the network when a verified copy is already available.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from .model_store import (
    MANIFEST_NAME,
    MODEL_STORE_ROOT,
    PROJECT_ROOT,
    has_model_files,
    is_prepared,
    prepared_files_dir,
    resolve_model_dir,
)


def prepare(*, force: bool = False, check_only: bool = False, verify: bool = False) -> Path:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    from .config import HybridConfig
    config = HybridConfig.from_env()
    model_path = resolve_model_dir(config.reranker_model, config.reranker_local_dir)

    if is_prepared(model_path, config.reranker_model, config.reranker_revision) and not force:
        existing_path = prepared_files_dir(model_path)
        print(f"[Hybrid] 기존 모델 준비 완료 (다운로드 생략): {existing_path}")
        if verify:
            _verify_offline_load(existing_path)
        return existing_path

    if check_only:
        raise RuntimeError(
            f"준비된 모델을 확인할 수 없습니다: {model_path}. "
            "`uv run --no-sync python -m src.hybrid.prepare_models`로 준비하세요."
        )

    if MODEL_STORE_ROOT in model_path.parents:
        MODEL_STORE_ROOT.parent.mkdir(parents=True, exist_ok=True)
        # Protect large model files even when the root repo has no .gitignore.
        (MODEL_STORE_ROOT.parent / ".gitignore").write_text("*\n!.gitignore\n", encoding="utf-8")

    model_path.mkdir(parents=True, exist_ok=True)
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError("huggingface-hub가 없습니다. pyproject.toml에 추가하고 uv sync를 실행하세요.") from exc

    # First try the default shared cache that previous CrossEncoder runs use.
    # This is OFFLINE and avoids an unnecessary second ~2.3 GB download.
    files_path: Path | None = None
    already_verified = False
    if not force:
        try:
            global_cached = Path(snapshot_download(
                repo_id=config.reranker_model,
                revision=config.reranker_revision,
                local_files_only=True,
            ))
            if has_model_files(global_cached):
                try:
                    _verify_offline_load(global_cached)
                    files_path = global_cached
                    already_verified = True
                    print(f"[Hybrid] 기존 Hugging Face 캐시 재사용: {files_path}")
                except Exception as exc:
                    print(f"[Hybrid] 기존 캐시 로딩 검증 실패 ({type(exc).__name__}); 새 다운로드를 시도합니다.")
        except Exception:
            # An offline cache miss (or stale cache metadata) is expected on
            # new machines; the real download will surface any fatal error.
            pass

    if files_path is None:
        print(f"[Hybrid] 모델 다운로드/캐시 확인: {config.reranker_model}")
        print(f"[Hybrid] 저장 경로: {model_path}")
        started = perf_counter()
        snapshot_download(
            repo_id=config.reranker_model,
            revision=config.reranker_revision,
            local_dir=str(model_path),
        )
        print(f"[Hybrid] 모델 파일 준비: {(perf_counter()-started):.1f}초")
        files_path = model_path
    if not has_model_files(files_path):
        raise RuntimeError(f"모델 가중치·토크나이저·config.json이 부족합니다: {files_path}")
    # Before marking ready, ensure that weights and tokenizer can be loaded
    # from disk without any Hugging Face network request.
    (model_path / MANIFEST_NAME).unlink(missing_ok=True)
    if not already_verified:
        _verify_offline_load(files_path)
    (model_path / MANIFEST_NAME).write_text(json.dumps({
        "model_name": config.reranker_model,
        "revision": config.reranker_revision,
        "files_path": str(files_path.resolve()),
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[Hybrid] 준비 완료. 이후 검색에서는 로컬 모델만 사용합니다.")
    return files_path


def _verify_offline_load(model_path: Path) -> None:
    try:
        from sentence_transformers import CrossEncoder
    except ImportError as exc:
        raise RuntimeError("sentence-transformers가 없습니다. uv sync로 의존성을 설치하세요.") from exc
    print("[Hybrid] 오프라인 모델/토크나이저 로딩 검증 중 (추론은 실행하지 않음)...")
    started = perf_counter()
    loaded = CrossEncoder(str(model_path), max_length=512, device="cpu", local_files_only=True)
    if loaded is None:
        raise RuntimeError("CrossEncoder에서 모델을 로드하지 못했습니다.")
    print(f"[Hybrid] 오프라인 로딩 검증: {(perf_counter()-started):.1f}초")
    del loaded


def main() -> None:
    parser = argparse.ArgumentParser(description="하이브리드 Reranker 모델을 다운로드하고 오프라인 로딩을 검증합니다")
    parser.add_argument("--force", action="store_true", help="기존 모델이 있어도 Hugging Face에서 갱신 확인")
    parser.add_argument("--check-only", action="store_true", help="다운로드/로딩 없이 설치 완료 여부 확인")
    parser.add_argument("--verify", action="store_true", help="기존 모델도 오프라인 로딩으로 재검증")
    args = parser.parse_args()
    if args.force and args.check_only:
        parser.error("--force와 --check-only는 동시에 사용할 수 없습니다")
    try:
        prepare(force=args.force, check_only=args.check_only, verify=args.verify)
    except Exception as exc:
        parser.exit(1, f"[Hybrid 모델 준비 실패] {type(exc).__name__}: {exc}\n")


if __name__ == "__main__":
    main()
