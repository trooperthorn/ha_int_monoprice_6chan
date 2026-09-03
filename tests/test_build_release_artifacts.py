"""Tests for scripts/build_release_artifacts.py (release automation)."""

from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.build_release_artifacts import build_archive, resolve_version


def _init_repo_with_tags(tmp_path: Path, tags: list[str]) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("test\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    for tag in tags:
        subprocess.run(["git", "tag", tag], cwd=tmp_path, check=True)
    return tmp_path


@pytest.fixture
def today() -> datetime:
    return datetime(2026, 9, 2, tzinfo=UTC)


def test_resolve_version_first_release_of_the_day(tmp_path: Path, today: datetime) -> None:
    repo = _init_repo_with_tags(tmp_path, [])
    assert resolve_version(repo, today=today) == "2026.09.02.00"


def test_resolve_version_increments_past_highest_existing_sequence(
    tmp_path: Path, today: datetime
) -> None:
    repo = _init_repo_with_tags(
        tmp_path, ["v2026.09.02.00", "v2026.09.02.01", "v2026.09.02.03"]
    )
    assert resolve_version(repo, today=today) == "2026.09.02.04"


def test_resolve_version_ignores_tags_from_other_days(
    tmp_path: Path, today: datetime
) -> None:
    repo = _init_repo_with_tags(tmp_path, ["v2026.09.01.05", "v2026.08.20.01"])
    assert resolve_version(repo, today=today) == "2026.09.02.00"


def test_resolve_version_ignores_unsuffixed_and_malformed_tags(
    tmp_path: Path, today: datetime
) -> None:
    repo = _init_repo_with_tags(
        tmp_path, ["v2026.09.02", "v2026.09.02.abc", "1.2.3", "v2026.09.02.02"]
    )
    assert resolve_version(repo, today=today) == "2026.09.02.03"


def test_build_archive_stamps_version_and_contains_component_files(
    tmp_path: Path,
) -> None:
    component_dir = tmp_path / "custom_components" / "monoprice_custom"
    component_dir.mkdir(parents=True)
    (component_dir / "manifest.json").write_text(
        json.dumps({"domain": "monoprice_custom", "version": "0.0.0"}),
        encoding="utf-8",
    )
    (component_dir / "__init__.py").write_text("", encoding="utf-8")
    translations_dir = component_dir / "translations"
    translations_dir.mkdir()
    (translations_dir / "en.json").write_text("{}", encoding="utf-8")

    output = tmp_path / "dist" / "monoprice_custom.zip"
    build_archive(tmp_path, "2026.09.02.00", output)

    assert output.exists()
    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
        assert names == {
            "manifest.json",
            "__init__.py",
            "translations/en.json",
        }
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["version"] == "2026.09.02.00"
        assert manifest["domain"] == "monoprice_custom"
