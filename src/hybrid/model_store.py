"""Stable project-local storage for the Hybrid Cross-Encoder model.

The selected model is downloaded during explicit setup, not while searching.
No Hugging Face SDK is imported from this module.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_STORE_ROOT = PROJECT_ROOT / ".models" / "hybrid"
MANIFEST_NAME = ".hybrid_model_ready.json"


def resolve_model_dir(model_name: str, override: str | Path | None = None) -> Path:
    """Return the same path in setup and runtime, independent of cwd/venv.

    HYBRID_RERANK_LOCAL_DIR may override the default; relative paths are
    interpreted relative to the project root, never the process working dir.
    """
    if override:
        path = Path(override).expanduser()
        return (path if path.is_absolute() else PROJECT_ROOT / path).resolve()
    # Human-readable directory name plus hash: safe for Windows and collision-free
    # when users switch between two Hugging Face model IDs.
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "--", model_name).strip(".-_")[:70] or "model"
    suffix = hashlib.sha256(model_name.encode("utf-8")).hexdigest()[:8]
    return MODEL_STORE_ROOT / f"{slug}-{suffix}"


def has_model_files(model_path: Path) -> bool:
    """Lightweight integrity check; CrossEncoder offline load is final proof."""
    if not (model_path / "config.json").is_file():
        return False
    has_weights = any((model_path / name).is_file() for name in (
        "model.safetensors", "model.safetensors.index.json",
        "pytorch_model.bin", "pytorch_model.bin.index.json",
    ))
    has_tokenizer = any((model_path / name).is_file() for name in (
        "tokenizer.json", "tokenizer.model", "sentencepiece.bpe.model", "vocab.txt",
    ))
    return has_weights and has_tokenizer


def read_manifest(model_path: Path) -> dict[str, Any] | None:
    try:
        content = json.loads((model_path / MANIFEST_NAME).read_text(encoding="utf-8"))
        return content if isinstance(content, dict) else None
    except (OSError, ValueError):
        return None


def prepared_files_dir(model_path: Path) -> Path:
    """Model may be reused directly from the user's existing HF snapshot."""
    manifest = read_manifest(model_path)
    if manifest and isinstance(manifest.get("files_path"), str):
        return Path(manifest["files_path"])
    return model_path


def is_prepared(model_path: Path, model_name: str, revision: str | None) -> bool:
    manifest = read_manifest(model_path)
    return bool(
        manifest is not None
        and manifest.get("model_name") == model_name
        and manifest.get("revision") == revision
        and has_model_files(prepared_files_dir(model_path))
    )
