import hashlib
from pathlib import Path


def file_sha256(file_path: Path) -> str:
    hasher = hashlib.sha256()

    with file_path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            hasher.update(block)

    return hasher.hexdigest()


def text_sha256(text: str) -> str:
    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()