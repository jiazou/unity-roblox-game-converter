"""
asset_extractor.py — Discovers and catalogues Unity project assets.

Walks the Unity project's Assets/ directory, fingerprints each file by
type (texture, mesh, audio, material, animation), and returns a structured
manifest that downstream modules and converter.py can reference.

No other module is imported here.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


AssetKind = Literal["texture", "mesh", "audio", "material", "animation", "unknown"]

_EXT_TO_KIND: dict[str, AssetKind] = {
    ".png": "texture", ".jpg": "texture", ".jpeg": "texture",
    ".tga": "texture", ".bmp": "texture",
    ".fbx": "mesh", ".obj": "mesh", ".dae": "mesh",
    ".wav": "audio", ".mp3": "audio", ".ogg": "audio",
    ".mat": "material",
    ".anim": "animation",
}


@dataclass
class AssetEntry:
    """Represents a single discovered Unity asset."""
    path: Path                  # Absolute path to the source file
    relative_path: Path         # Path relative to the Unity project root
    kind: AssetKind             # Semantic category
    size_bytes: int             # File size in bytes
    sha256: str                 # Content hash for deduplication
    meta_path: Path | None      # Companion .meta file, if present


@dataclass
class AssetManifest:
    """Complete catalogue of all extractable assets in a Unity project."""
    unity_project_path: Path
    assets: list[AssetEntry] = field(default_factory=list)

    # Convenience look-ups populated after extraction
    by_kind: dict[AssetKind, list[AssetEntry]] = field(default_factory=dict)
    by_sha256: dict[str, AssetEntry] = field(default_factory=dict)  # dedup map

    @property
    def total_size_bytes(self) -> int:
        return sum(a.size_bytes for a in self.assets)


def _sha256_of(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while data := fh.read(chunk):
            h.update(data)
    return h.hexdigest()


def extract_assets(
    unity_project_path: str | Path,
    supported_extensions: list[str] | None = None,
) -> AssetManifest:
    """
    Walk *unity_project_path*/Assets and build a complete AssetManifest.

    Args:
        unity_project_path: Root directory of the Unity project.
        supported_extensions: File extensions to include (e.g. [".png", ".fbx"]).
                              Defaults to all kinds defined in _EXT_TO_KIND.

    Returns:
        AssetManifest with all discovered assets indexed by kind and hash.

    Raises:
        FileNotFoundError: If the Assets/ subdirectory does not exist.
    """
    root = Path(unity_project_path).resolve()
    assets_dir = root / "Assets"
    if not assets_dir.is_dir():
        raise FileNotFoundError(f"Unity Assets directory not found: {assets_dir}")

    allowed = set(supported_extensions or _EXT_TO_KIND.keys())
    manifest = AssetManifest(unity_project_path=root)

    for dirpath, _dirs, filenames in os.walk(assets_dir):
        for fname in filenames:
            fpath = Path(dirpath) / fname
            ext = fpath.suffix.lower()

            if ext == ".meta":
                continue  # handled as companion below
            if ext not in allowed:
                continue

            kind: AssetKind = _EXT_TO_KIND.get(ext, "unknown")
            meta = fpath.with_suffix(fpath.suffix + ".meta")
            entry = AssetEntry(
                path=fpath,
                relative_path=fpath.relative_to(root),
                kind=kind,
                size_bytes=fpath.stat().st_size,
                sha256=_sha256_of(fpath),
                meta_path=meta if meta.exists() else None,
            )
            manifest.assets.append(entry)
            manifest.by_kind.setdefault(kind, []).append(entry)
            manifest.by_sha256.setdefault(entry.sha256, entry)

    return manifest
