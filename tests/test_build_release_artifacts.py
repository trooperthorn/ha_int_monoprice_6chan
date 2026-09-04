"""Tests for the release scripts: version validation, writing, and the archive."""

from __future__ import annotations

import json
import stat
import sys
import zipfile
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_release_artifacts import (
    build_archive,
    validate_versions,
)
from scripts.set_version import next_calver, parse_calver, set_version

EXPECTED_VERSION = json.loads(
    (ROOT / "custom_components/monoprice_custom/manifest.json").read_text(encoding="utf-8")
)["version"]


def _repo(tmp_path: Path, version: str = "2026.09.02.2") -> Path:
    repository = tmp_path / "repository"
    component = repository / "custom_components" / "monoprice_custom"
    component.mkdir(parents=True)
    (repository / ".release.json").write_text(
        (ROOT / ".release.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (component / "manifest.json").write_text(
        json.dumps({"domain": "monoprice_custom", "version": version}, indent=2) + "\n",
        encoding="utf-8",
    )
    (component / "__init__.py").write_text("", encoding="utf-8")
    (component / "translations").mkdir()
    (component / "translations" / "en.json").write_text("{}", encoding="utf-8")
    (component / "__pycache__").mkdir()
    (component / "__pycache__" / "x.pyc").write_bytes(b"")
    return repository


def test_repository_manifest_version_validates() -> None:
    assert validate_versions(ROOT) == EXPECTED_VERSION


def test_next_calver_uses_highest_sequence_for_release_date() -> None:
    assert (
        next_calver(
            ["v2026.09.01.9", "v2026.09.02.1", "v2026.09.02.4", "v2026.09.02.00", "1.2.3"],
            date(2026, 9, 2),
        )
        == "2026.09.02.5"
    )


def test_next_calver_starts_new_day_at_one() -> None:
    assert next_calver(["v2026.09.02.8"], date(2026, 9, 3)) == "2026.09.03.1"


def test_parse_calver_rejects_invalid_versions() -> None:
    for value in ("2026.02.30.1", "2026.9.02.1", "2026.09.02.0", "v2026.09.02.1"):
        with pytest.raises(ValueError):
            parse_calver(value)


def test_set_version_writes_the_manifest_and_validates(tmp_path: Path) -> None:
    repository = _repo(tmp_path)
    manifest = repository / "custom_components/monoprice_custom/manifest.json"
    original_mode = stat.S_IMODE(manifest.stat().st_mode)

    set_version(repository, "2026.09.02.3")

    assert validate_versions(repository) == "2026.09.02.3"
    assert stat.S_IMODE(manifest.stat().st_mode) == original_mode


def test_validate_rejects_malformed_version(tmp_path: Path) -> None:
    repository = _repo(tmp_path, version="2026.9.2.01")
    with pytest.raises(ValueError):
        validate_versions(repository)


def test_build_archive_is_reproducible_and_hacs_compatible(tmp_path: Path) -> None:
    repository = _repo(tmp_path)
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"

    first_version, first_digest = build_archive(repository, first)
    second_version, second_digest = build_archive(repository, second)

    assert first_version == second_version == "2026.09.02.2"
    assert first_digest == second_digest
    assert first.read_bytes() == second.read_bytes()

    with zipfile.ZipFile(first) as archive:
        names = set(archive.namelist())
        assert names == {"manifest.json", "__init__.py", "translations/en.json"}
        assert json.loads(archive.read("manifest.json"))["version"] == "2026.09.02.2"
