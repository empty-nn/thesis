from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from schemas.metadata_schema import TourismMetadata


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_json(data: Dict[str, Any], output_path: str | Path) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def hash_file(file_path: str | Path) -> str:
    file_path = Path(file_path)
    hasher = hashlib.sha256()

    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)

    return hasher.hexdigest()


def safe_filename(name: str) -> str:
    name = re.sub(r"[^\w\-]+", "_", name)
    name = re.sub(r"_+", "_", name)
    return name.strip("_").lower()

def metadata_to_dict(metadata: TourismMetadata) -> Dict[str, Any]:
    """
    Compatible with Pydantic v1 and v2.
    """

    if hasattr(metadata, "model_dump"):
        return metadata.model_dump()

    if hasattr(metadata, "dict"):
        return metadata.dict()

    return {}

def safe_list(value: Optional[Any]) -> List[Any]:
    if value is None:
        return []

    if isinstance(value, list):
        return value

    return [value]

def safe_float(value: Optional[Any], default: float = 0.0) -> float:
    try:
        if value is None:
            return default

        return float(value)

    except Exception:
        return default
