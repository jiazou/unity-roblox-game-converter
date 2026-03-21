"""
mesh_decimator.py — Conservative mesh decimation for Unity → Roblox conversion.

Roblox imposes hard limits on MeshPart geometry (10 000 polygons per MeshPart).
This module loads Unity mesh assets (.fbx, .obj, .dae), analyses their polygon
count, and applies *conservative* decimation only when necessary to bring them
under budget.

Conservative means:
  - Meshes already under the target face count are left untouched.
  - Decimation targets no more than the minimum reduction needed.
  - A generous quality floor prevents visually destructive simplification.
  - The original files are never modified — decimated copies are written to the
    output directory.

No other module is imported here.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Roblox geometry limits and conservative defaults
# ---------------------------------------------------------------------------

ROBLOX_MAX_FACES: int = 10_000          # hard MeshPart limit
DEFAULT_TARGET_FACES: int = 8_000       # leave headroom below the cap
QUALITY_FLOOR: float = 0.6             # never reduce below 60% of original
MIN_FACES_TO_DECIMATE: int = 500       # don't bother decimating tiny meshes


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class MeshStats:
    """Geometry statistics for a single mesh file."""
    path: Path
    vertices: int = 0
    faces: int = 0
    file_size_bytes: int = 0
    is_valid: bool = True
    error: str = ""


@dataclass
class DecimationEntry:
    """Result of decimating a single mesh."""
    source_path: Path                # original file
    output_path: Path                # decimated copy (or original if untouched)
    original_faces: int = 0
    final_faces: int = 0
    reduction_ratio: float = 1.0     # 1.0 = no reduction
    was_decimated: bool = False
    was_copied: bool = False         # True when copied without decimation
    skipped: bool = False            # True if load/parse failed
    error: str = ""


@dataclass
class DecimationResult:
    """Aggregate outcome for all meshes processed."""
    entries: list[DecimationEntry] = field(default_factory=list)
    total_meshes: int = 0
    decimated: int = 0
    already_compliant: int = 0
    skipped: int = 0
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Mesh loading helpers (trimesh)
# ---------------------------------------------------------------------------

def _find_assimp_cli() -> str | None:
    """Find the ``assimp`` CLI tool (installed via ``brew install assimp``)."""
    import shutil
    return shutil.which("assimp")


_assimp_cli = _find_assimp_cli()


def _load_fbx_as_trimesh(mesh_path: Path):
    """Load an FBX file by converting to OBJ via the assimp CLI, then loading with trimesh.

    Requires ``brew install assimp`` on macOS.  Returns None if conversion fails.
    """
    import subprocess
    import tempfile
    import trimesh  # type: ignore

    if not _assimp_cli:
        return None

    with tempfile.NamedTemporaryFile(suffix=".obj", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            [_assimp_cli, "export", str(mesh_path), tmp_path],
            capture_output=True, timeout=30,
        )
        if result.returncode != 0:
            return None
        return trimesh.load(tmp_path, force="mesh", process=False)
    except Exception:
        return None
    finally:
        Path(tmp_path).unlink(missing_ok=True)
        # assimp also creates a .mtl file
        Path(tmp_path.replace(".obj", ".mtl")).unlink(missing_ok=True)


def _load_mesh_stats(mesh_path: Path) -> MeshStats:
    """
    Load a mesh file and return its vertex/face counts.

    Uses trimesh if available; falls back to a lightweight OBJ face counter
    for .obj files when trimesh is not installed.
    """
    stats = MeshStats(path=mesh_path, file_size_bytes=mesh_path.stat().st_size)

    try:
        import trimesh  # type: ignore

        mesh = trimesh.load(str(mesh_path), force="mesh", process=False)
        stats.vertices = len(mesh.vertices)
        stats.faces = len(mesh.faces)
        return stats
    except ImportError:
        pass
    except NotImplementedError:
        # trimesh doesn't support this format (e.g. FBX) — try pyassimp.
        if mesh_path.suffix.lower() in (".fbx",):
            try:
                mesh = _load_fbx_as_trimesh(mesh_path)
                if mesh is not None and len(mesh.vertices) > 0:
                    stats.vertices = len(mesh.vertices)
                    stats.faces = len(mesh.faces)
                    return stats
                stats.is_valid = False
                stats.error = f"FBX loaded but contained no geometry"
                return stats
            except Exception as exc:  # noqa: BLE001
                stats.is_valid = False
                stats.error = f"pyassimp FBX load failed: {exc}"
                return stats
    except Exception as exc:  # noqa: BLE001
        stats.is_valid = False
        stats.error = f"trimesh load failed: {exc}"
        return stats

    # Lightweight fallback for .obj files
    if mesh_path.suffix.lower() == ".obj":
        try:
            face_count = 0
            vert_count = 0
            for line in mesh_path.read_text(errors="replace").splitlines():
                if line.startswith("f "):
                    # Count triangulated faces: n-gon → (n-2) triangles
                    num_verts = len(line.split()) - 1  # subtract "f" token
                    face_count += max(1, num_verts - 2)
                elif line.startswith("v "):
                    vert_count += 1
            stats.faces = face_count
            stats.vertices = vert_count
            return stats
        except OSError as exc:
            stats.is_valid = False
            stats.error = str(exc)
            return stats

    stats.is_valid = False
    stats.error = "trimesh not installed; only .obj fallback supported"
    return stats


def _decimate_mesh(
    mesh_path: Path,
    output_path: Path,
    target_faces: int,
) -> tuple[int, int]:
    """
    Decimate a mesh to *target_faces* and save to *output_path*.

    Returns (original_faces, final_faces).
    Requires trimesh with the simplification backend.
    """
    import trimesh  # type: ignore

    try:
        mesh = trimesh.load(str(mesh_path), force="mesh", process=False)
    except NotImplementedError:
        # FBX not supported by trimesh — fall back to pyassimp
        mesh = _load_fbx_as_trimesh(mesh_path)
        if mesh is None:
            raise ValueError(f"Could not load {mesh_path}")
    original_faces = len(mesh.faces)

    if original_faces <= target_faces:
        # Already under budget — write unchanged
        mesh.export(str(output_path))
        return original_faces, original_faces

    simplified = mesh.simplify_quadric_decimation(target_faces)
    simplified.export(str(output_path))
    return original_faces, len(simplified.faces)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def decimate_meshes(
    mesh_paths: list[Path],
    output_dir: Path,
    target_faces: int = DEFAULT_TARGET_FACES,
    quality_floor: float = QUALITY_FLOOR,
    roblox_max_faces: int = ROBLOX_MAX_FACES,
) -> DecimationResult:
    """
    Analyse and conservatively decimate a list of mesh files.

    Strategy:
      1. Load mesh and count faces.
      2. If faces <= roblox_max_faces → copy unchanged.
      3. If faces > roblox_max_faces → decimate to *target_faces*, but never
         reduce below quality_floor × original_faces.
      4. Original files are never modified.

    Args:
        mesh_paths: Mesh files to process (.fbx, .obj, .dae).
        output_dir: Directory for decimated/copied output meshes.
        target_faces: Desired face count after decimation.
        quality_floor: Minimum ratio of faces to keep (0.0–1.0).
        roblox_max_faces: The hard face limit above which decimation triggers.

    Returns:
        DecimationResult summarising all meshes processed.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    result = DecimationResult()

    for mesh_path in mesh_paths:
        result.total_meshes += 1
        entry = DecimationEntry(
            source_path=mesh_path,
            output_path=output_dir / mesh_path.name,
        )

        # ── Load stats ─────────────────────────────────────────────
        stats = _load_mesh_stats(mesh_path)
        if not stats.is_valid:
            # Cannot analyse the mesh, but still copy it to the output
            # directory so downstream stages (rbxl_writer, uploader) have
            # a mesh file to work with.
            try:
                shutil.copy2(mesh_path, entry.output_path)
                entry.was_copied = True
                entry.final_faces = 0  # unknown
                entry.reduction_ratio = 1.0
                result.already_compliant += 1
                result.warnings.append(
                    f"{mesh_path.name}: {stats.error}. "
                    f"Copied without analysis."
                )
            except OSError:
                entry.skipped = True
                entry.error = stats.error
                result.skipped += 1
                result.warnings.append(f"Skipped {mesh_path.name}: {stats.error}")
            result.entries.append(entry)
            continue

        entry.original_faces = stats.faces

        # ── Already compliant — copy unchanged ─────────────────────
        if stats.faces <= roblox_max_faces:
            try:
                shutil.copy2(mesh_path, entry.output_path)
                entry.was_copied = True
                entry.final_faces = stats.faces
                entry.reduction_ratio = 1.0
                result.already_compliant += 1
            except OSError as exc:
                entry.skipped = True
                entry.error = str(exc)
                result.skipped += 1
            result.entries.append(entry)
            continue

        # ── Needs decimation ───────────────────────────────────────
        # Apply the quality floor: never go below quality_floor × original
        floor_faces = max(
            int(stats.faces * quality_floor),
            MIN_FACES_TO_DECIMATE,
        )
        effective_target = max(target_faces, floor_faces)

        # If even the quality floor exceeds the Roblox limit, honour the
        # hard cap but warn the user.
        if effective_target > roblox_max_faces:
            effective_target = roblox_max_faces
            result.warnings.append(
                f"{mesh_path.name}: quality floor ({floor_faces} faces) exceeds "
                f"Roblox limit ({roblox_max_faces}). Clamped — expect visible loss."
            )

        try:
            orig, final = _decimate_mesh(mesh_path, entry.output_path, effective_target)
            entry.final_faces = final
            entry.reduction_ratio = final / max(orig, 1)
            entry.was_decimated = True
            result.decimated += 1
        except ImportError:
            # trimesh not available — copy original with a warning
            shutil.copy2(mesh_path, entry.output_path)
            entry.was_copied = True
            entry.final_faces = stats.faces
            entry.reduction_ratio = 1.0
            result.already_compliant += 1
            result.warnings.append(
                f"{mesh_path.name}: trimesh not installed, copied without decimation "
                f"({stats.faces} faces, Roblox limit is {roblox_max_faces})."
            )
        except Exception as exc:  # noqa: BLE001
            # Decimation failed — copy original as fallback so downstream
            # pipeline stages still have a mesh to work with.
            try:
                shutil.copy2(mesh_path, entry.output_path)
                entry.was_copied = True
                entry.final_faces = stats.faces
                entry.reduction_ratio = 1.0
            except OSError:
                entry.skipped = True
                entry.error = str(exc)
                result.skipped += 1
            result.warnings.append(
                f"Decimation failed for {mesh_path.name}: {exc}. "
                f"Original mesh copied as fallback."
            )

        result.entries.append(entry)

    return result
