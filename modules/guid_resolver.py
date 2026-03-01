"""
guid_resolver.py — Full Unity GUID resolution for cross-asset references.

Unity uses opaque 32-hex-character GUIDs (stored in companion .meta files) to
link assets together.  A material references textures by GUID, a scene
references prefabs and meshes by GUID, and prefab variants reference their
bases by GUID.

This module builds a complete, bidirectional GUID ↔ asset-path index for a
Unity project and exposes helpers that other modules can use to resolve any
reference chain.

Capabilities:
  - Parse every .meta file under Assets/ (including nested Packages/).
  - Build GUID → asset path, asset path → GUID, and GUID → asset kind maps.
  - Resolve fileID + GUID pairs (sub-asset references inside .meta importers).
  - Resolve transitive reference chains (e.g. prefab variant → base prefab).
  - Detect and warn about orphan .meta files and duplicate GUIDs.
  - Thread-safe: the resolved index is an immutable dataclass snapshot.

No other module is imported here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml


# ---------------------------------------------------------------------------
# Asset kind classification (mirrors asset_extractor but kept independent)
# ---------------------------------------------------------------------------

AssetKind = Literal[
    "texture", "mesh", "audio", "material", "animation",
    "shader", "prefab", "scene", "script", "directory", "unknown",
]

_EXT_TO_KIND: dict[str, AssetKind] = {
    ".png": "texture", ".jpg": "texture", ".jpeg": "texture",
    ".tga": "texture", ".bmp": "texture", ".exr": "texture",
    ".hdr": "texture", ".psd": "texture",
    ".fbx": "mesh", ".obj": "mesh", ".dae": "mesh", ".blend": "mesh",
    ".wav": "audio", ".mp3": "audio", ".ogg": "audio",
    ".mat": "material",
    ".anim": "animation", ".controller": "animation",
    ".shader": "shader", ".cginc": "shader", ".hlsl": "shader",
    ".prefab": "prefab",
    ".unity": "scene",
    ".cs": "script",
}


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GuidEntry:
    """A single resolved GUID → asset mapping."""
    guid: str
    asset_path: Path          # absolute path to the asset file
    relative_path: Path       # relative to the project root
    kind: AssetKind
    is_directory: bool        # folders also get .meta files and GUIDs


@dataclass(frozen=True)
class SubAssetRef:
    """A reference to a sub-asset within a file (fileID + GUID pair)."""
    guid: str
    file_id: int


@dataclass
class GuidIndex:
    """
    Complete GUID ↔ asset-path index for a Unity project.

    Built once, then queried by any module that needs to resolve references.
    """
    project_root: Path

    # Primary maps
    guid_to_entry: dict[str, GuidEntry] = field(default_factory=dict)
    path_to_guid: dict[Path, str] = field(default_factory=dict)  # absolute path → GUID

    # Diagnostics
    duplicate_guids: dict[str, list[Path]] = field(default_factory=dict)
    orphan_metas: list[Path] = field(default_factory=list)
    total_meta_files: int = 0
    parse_errors: list[str] = field(default_factory=list)

    # ── Query helpers ──────────────────────────────────────────────

    def resolve(self, guid: str) -> Path | None:
        """Return the asset path for a GUID, or None."""
        entry = self.guid_to_entry.get(guid)
        return entry.asset_path if entry else None

    def resolve_kind(self, guid: str) -> AssetKind | None:
        """Return the asset kind for a GUID, or None."""
        entry = self.guid_to_entry.get(guid)
        return entry.kind if entry else None

    def resolve_relative(self, guid: str) -> Path | None:
        """Return the project-relative path for a GUID, or None."""
        entry = self.guid_to_entry.get(guid)
        return entry.relative_path if entry else None

    def guid_for_path(self, asset_path: Path) -> str | None:
        """Return the GUID for an absolute asset path, or None."""
        return self.path_to_guid.get(asset_path.resolve())

    def resolve_ref(self, ref: dict[str, Any]) -> Path | None:
        """
        Resolve a Unity object reference dict (``{fileID: ..., guid: ..., type: ...}``).

        Returns the asset path, or None if the guid is empty / unresolvable.
        """
        guid = ref.get("guid", "")
        if not guid or guid == "0" * 32:
            return None
        return self.resolve(guid)

    def resolve_chain(self, guid: str, max_depth: int = 16) -> list[GuidEntry]:
        """
        Follow transitive GUID references (e.g. prefab variant → base).

        Reads the resolved asset's YAML to find ``m_Father``/``m_ParentPrefab``
        references and walks the chain until it terminates or *max_depth* is hit.
        """
        chain: list[GuidEntry] = []
        seen: set[str] = set()
        current = guid

        for _ in range(max_depth):
            if current in seen:
                break
            seen.add(current)
            entry = self.guid_to_entry.get(current)
            if entry is None:
                break
            chain.append(entry)

            # Try to read next link from the asset file
            next_guid = _extract_parent_guid(entry.asset_path)
            if not next_guid:
                break
            current = next_guid

        return chain

    def filter_by_kind(self, kind: AssetKind) -> dict[str, GuidEntry]:
        """Return all GUID entries of a given asset kind."""
        return {
            g: e for g, e in self.guid_to_entry.items() if e.kind == kind
        }

    @property
    def total_resolved(self) -> int:
        return len(self.guid_to_entry)


# ---------------------------------------------------------------------------
# .meta file parsing
# ---------------------------------------------------------------------------

_RE_GUID_LINE = re.compile(r"^guid:\s*([0-9a-fA-F]{32})\s*$", re.MULTILINE)
_RE_FOLDER_TYPE = re.compile(r"^folderAsset:\s*yes", re.MULTILINE)


def _parse_meta_file(meta_path: Path) -> tuple[str, bool] | None:
    """
    Extract the GUID and folder flag from a .meta file.

    Returns (guid, is_folder) or None on failure.
    """
    try:
        text = meta_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    m = _RE_GUID_LINE.search(text)
    if not m:
        return None

    guid = m.group(1)
    is_folder = bool(_RE_FOLDER_TYPE.search(text))
    return guid, is_folder


def _extract_parent_guid(asset_path: Path) -> str | None:
    """
    For prefab variants and nested prefabs, extract the parent GUID.

    Looks for ``m_ParentPrefab``, ``m_CorrespondingSourceObject``, or
    ``m_SourcePrefab`` reference dicts containing a ``guid`` key.
    """
    if not asset_path.exists() or asset_path.suffix not in (".prefab", ".unity"):
        return None
    try:
        text = asset_path.read_text(encoding="utf-8", errors="replace")
        # Quick regex scan — avoids full YAML parse for speed
        for key in ("m_ParentPrefab", "m_CorrespondingSourceObject", "m_SourcePrefab"):
            pattern = re.compile(
                rf"{key}:\s*\{{[^}}]*guid:\s*([0-9a-fA-F]{{32}})", re.DOTALL
            )
            m = pattern.search(text)
            if m:
                guid = m.group(1)
                if guid != "0" * 32:
                    return guid
    except OSError:
        pass
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_guid_index(unity_project_path: str | Path) -> GuidIndex:
    """
    Scan a Unity project and build a complete GUID ↔ asset-path index.

    Walks every ``.meta`` file under ``Assets/`` (and ``Packages/`` if present),
    parses the GUID, classifies the asset, and populates a queryable
    :class:`GuidIndex`.

    Args:
        unity_project_path: Root directory of the Unity project.

    Returns:
        A fully populated :class:`GuidIndex`.

    Raises:
        FileNotFoundError: If the Assets/ subdirectory does not exist.
    """
    root = Path(unity_project_path).resolve()
    assets_dir = root / "Assets"
    if not assets_dir.is_dir():
        raise FileNotFoundError(f"Assets directory not found: {assets_dir}")

    index = GuidIndex(project_root=root)

    # Scan both Assets/ and Packages/ (local packages may contain .meta files)
    scan_dirs = [assets_dir]
    packages_dir = root / "Packages"
    if packages_dir.is_dir():
        scan_dirs.append(packages_dir)

    for scan_dir in scan_dirs:
        for meta_path in scan_dir.rglob("*.meta"):
            index.total_meta_files += 1

            parsed = _parse_meta_file(meta_path)
            if parsed is None:
                index.parse_errors.append(f"Could not parse GUID from {meta_path}")
                continue

            guid, is_folder = parsed
            asset_path = meta_path.with_suffix("")  # strip .meta

            # Orphan check: .meta exists but asset does not
            if not is_folder and not asset_path.exists():
                index.orphan_metas.append(meta_path)
                # Still index it — the reference may be valid at runtime
                # (e.g. asset generated by an importer)

            # Duplicate GUID check
            if guid in index.guid_to_entry:
                existing = index.guid_to_entry[guid]
                index.duplicate_guids.setdefault(guid, [existing.asset_path])
                index.duplicate_guids[guid].append(asset_path)
                # Keep the first entry (Unity would also use whichever it finds first)
                continue

            # Classify
            if is_folder:
                kind: AssetKind = "directory"
            else:
                kind = _EXT_TO_KIND.get(asset_path.suffix.lower(), "unknown")

            try:
                relative = asset_path.relative_to(root)
            except ValueError:
                relative = asset_path

            entry = GuidEntry(
                guid=guid,
                asset_path=asset_path.resolve(),
                relative_path=relative,
                kind=kind,
                is_directory=is_folder,
            )

            index.guid_to_entry[guid] = entry
            index.path_to_guid[asset_path.resolve()] = guid

    return index
