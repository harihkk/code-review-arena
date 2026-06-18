"""Content-addressed evidence bundle: make a saved run tamper-evident.

After a run, every artifact in its directory is hashed into ``checksums.json``
plus a single ``bundle_id`` (sha256 over the canonical name->hash map).
``arena verify-run`` recomputes those hashes and reports any artifact that was
added, removed, or edited after the fact. Pinning the ``bundle_id`` out of band
(``--expected-id``) also catches a fully consistent rewrite.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

CHECKSUMS_FILENAME = "checksums.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_hashes(run_dir: Path) -> dict[str, str]:
    """Hash every top-level file in the run dir except the checksums file itself."""
    return {
        path.name: _sha256(path)
        for path in sorted(run_dir.iterdir())
        if path.is_file() and path.name != CHECKSUMS_FILENAME
    }


def bundle_id(file_hashes: dict[str, str]) -> str:
    canonical = json.dumps(file_hashes, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def write_bundle_checksums(run_dir: Path) -> str:
    """Hash the run's artifacts into checksums.json and return the bundle id."""
    hashes = _file_hashes(run_dir)
    identifier = bundle_id(hashes)
    (run_dir / CHECKSUMS_FILENAME).write_text(
        json.dumps({"bundle_id": identifier, "files": hashes}, indent=2) + "\n",
        encoding="utf-8",
    )
    return identifier


@dataclass
class BundleVerification:
    ok: bool
    bundle_id: str | None = None
    bundle_id_ok: bool = True
    missing: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    expected_id_ok: bool = True
    error: str | None = None


def verify_bundle(run_dir: Path, *, expected_id: str | None = None) -> BundleVerification:
    checksums = run_dir / CHECKSUMS_FILENAME
    if not checksums.is_file():
        return BundleVerification(ok=False, error="no checksums.json (not a v2 evidence bundle)")
    try:
        recorded = json.loads(checksums.read_text(encoding="utf-8"))
        recorded_files: dict[str, str] = recorded["files"]
        recorded_id: str | None = recorded.get("bundle_id")
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        return BundleVerification(ok=False, error=f"unreadable checksums.json: {exc}")

    current = _file_hashes(run_dir)
    missing = sorted(set(recorded_files) - set(current))
    added = sorted(set(current) - set(recorded_files))
    modified = sorted(
        name for name in set(recorded_files) & set(current) if recorded_files[name] != current[name]
    )
    # checksums.json must be self-consistent (its recorded id matches its file map).
    bundle_id_ok = recorded_id == bundle_id(recorded_files)
    expected_id_ok = expected_id is None or recorded_id == expected_id
    ok = not missing and not added and not modified and bundle_id_ok and expected_id_ok
    return BundleVerification(
        ok=ok,
        bundle_id=recorded_id,
        bundle_id_ok=bundle_id_ok,
        missing=missing,
        modified=modified,
        added=added,
        expected_id_ok=expected_id_ok,
    )
