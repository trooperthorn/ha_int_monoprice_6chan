"""Build deterministic release artifacts for the Monoprice HACS integration.

The release version is resolved automatically from git tag history (CalVer
with a same-day sequence counter), so nobody has to bump
custom_components/monoprice_custom/manifest.json by hand before merging.
Used by .github/workflows/release.yaml.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import zipfile
from datetime import UTC, datetime
from pathlib import Path

DOMAIN = "monoprice_custom"
COMPONENT_DIR = Path("custom_components") / DOMAIN
TAG_PATTERN = re.compile(r"^v(?P<date>\d{4}\.\d{2}\.\d{2})\.(?P<seq>\d+)$")


def resolve_version(repo_root: Path, *, today: datetime | None = None) -> str:
    """Return the next CalVer version (YYYY.MM.DD.NN) for today.

    Reads existing `v{date}.{seq}` tags and picks one past the highest
    sequence already used today, so reruns and same-day releases never
    collide. Matches only the full `v{date}.{seq}` shape, unlike the prior
    `git tag -l "v${CALVER}*"` glob this replaces, which also matched
    differently-suffixed and un-suffixed tags and produced duplicate or
    malformed sequence numbers under concurrent runs (e.g. v2026.08.13.99
    and v2026.08.20.000 alongside v2026.08.20.01).
    """
    date = (today or datetime.now(UTC)).strftime("%Y.%m.%d")
    result = subprocess.run(
        ["git", "tag", "-l", f"v{date}.*"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    highest_seq = -1
    for tag in result.stdout.splitlines():
        match = TAG_PATTERN.match(tag.strip())
        if match and match.group("date") == date:
            highest_seq = max(highest_seq, int(match.group("seq")))
    return f"{date}.{highest_seq + 1:02d}"


def build_archive(repo_root: Path, version: str, output: Path) -> Path:
    """Zip the integration's component directory with `version` stamped in.

    Deterministic: files are added in sorted order and manifest.json is
    rewritten with the resolved version, so the same inputs always produce
    the same archive contents.
    """
    component_dir = repo_root / COMPONENT_DIR
    manifest_path = component_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["version"] = version

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(component_dir.rglob("*")):
            if path.is_dir():
                continue
            arcname = path.relative_to(component_dir).as_posix()
            if path == manifest_path:
                archive.writestr(arcname, json.dumps(manifest, indent=2) + "\n")
            else:
                archive.write(path, arcname)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version", required=True, help="Version to stamp into manifest.json"
    )
    parser.add_argument(
        "--output", required=True, type=Path, help="Path to write the zip archive"
    )
    args = parser.parse_args()
    build_archive(Path.cwd(), args.version, args.output)


if __name__ == "__main__":
    main()
