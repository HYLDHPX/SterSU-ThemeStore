"""Store verified theme assets at immutable, versioned repository paths."""

from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path

from validate_catalog import ID_RE, ValidationFailure

MAX_REPOSITORY_FILE_BYTES = 100 * 1024 * 1024
REPOSITORY_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")


def package_relative_path(theme_id: str, version_code: int) -> Path:
    if not ID_RE.fullmatch(theme_id) or version_code < 1:
        raise ValidationFailure("invalid repository package identity")
    return Path("theme-store/packages") / theme_id / f"v{version_code}" / f"{theme_id}-v{version_code}.kstheme"


def repository_url(repository: str, relative_path: Path) -> str:
    if not REPOSITORY_RE.fullmatch(repository):
        raise ValidationFailure("invalid GitHub repository name")
    return f"https://raw.githubusercontent.com/{repository}/main/{relative_path.as_posix()}"


def stage_package(source: Path, repository_root: Path, theme_id: str, version_code: int) -> Path:
    size = source.stat().st_size
    if not 0 < size <= MAX_REPOSITORY_FILE_BYTES:
        raise ValidationFailure("repository packages must be at most 100 MiB; reduce the theme assets before publishing")
    destination = repository_root / package_relative_path(theme_id, version_code)
    if repository_root.resolve() not in destination.resolve().parents:
        raise ValidationFailure("repository package path escapes checkout")
    if destination.exists():
        if destination.stat().st_size != size or hashlib.sha256(destination.read_bytes()).digest() != hashlib.sha256(source.read_bytes()).digest():
            raise ValidationFailure("published package path already contains different bytes; increase versionCode")
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with source.open("rb") as input_file, destination.open("xb") as output_file:
            created = True
            shutil.copyfileobj(input_file, output_file)
    except OSError:
        if created:
            destination.unlink(missing_ok=True)
        raise
    return destination
