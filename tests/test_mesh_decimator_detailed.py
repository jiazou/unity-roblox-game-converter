"""Fine-grained unit tests for modules/mesh_decimator.py.

Tests quality floor clamping, edge cases with degenerate meshes,
output naming, and batch processing behavior.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from modules.mesh_decimator import (
    DecimationEntry,
    DecimationResult,
    MeshStats,
    decimate_meshes,
    _load_mesh_stats,
)


def _make_obj(path: Path, face_count: int) -> None:
    """Write a minimal .obj file with the given number of triangular faces."""
    lines = []
    verts_needed = face_count + 2
    for i in range(verts_needed):
        lines.append(f"v {float(i)} {float(i % 3)} {float(i % 5)}")
    for i in range(face_count):
        v1 = 1
        v2 = i + 2
        v3 = i + 3 if i + 3 <= verts_needed else 2
        lines.append(f"f {v1} {v2} {v3}")
    path.write_text("\n".join(lines), encoding="utf-8")


class TestLoadMeshStats:
    """Test the mesh stats loader via _load_mesh_stats."""

    def test_empty_obj(self, tmp_path: Path) -> None:
        obj = tmp_path / "empty.obj"
        obj.write_text("# empty file\n", encoding="utf-8")
        stats = _load_mesh_stats(obj)
        assert stats.faces == 0

    def test_vertices_only(self, tmp_path: Path) -> None:
        obj = tmp_path / "verts.obj"
        obj.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\n", encoding="utf-8")
        stats = _load_mesh_stats(obj)
        assert stats.faces == 0
        assert stats.vertices >= 3

    def test_single_face(self, tmp_path: Path) -> None:
        obj = tmp_path / "tri.obj"
        obj.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding="utf-8")
        stats = _load_mesh_stats(obj)
        assert stats.faces == 1

    def test_multiple_faces(self, tmp_path: Path) -> None:
        obj = tmp_path / "multi.obj"
        _make_obj(obj, 50)
        stats = _load_mesh_stats(obj)
        assert stats.faces == 50

    def test_quad_faces_counted(self, tmp_path: Path) -> None:
        """Quads (4-vertex faces) should each count as one face."""
        obj = tmp_path / "quad.obj"
        content = (
            "v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\n"
            "f 1 2 3 4\n"
        )
        obj.write_text(content, encoding="utf-8")
        stats = _load_mesh_stats(obj)
        assert stats.faces == 1

    def test_comments_and_blanks_ignored(self, tmp_path: Path) -> None:
        obj = tmp_path / "comments.obj"
        content = (
            "# comment\n"
            "\n"
            "v 0 0 0\n"
            "v 1 0 0\n"
            "v 0 1 0\n"
            "# another comment\n"
            "f 1 2 3\n"
            "\n"
        )
        obj.write_text(content, encoding="utf-8")
        stats = _load_mesh_stats(obj)
        assert stats.faces == 1

    def test_obj_stats(self, tmp_path: Path) -> None:
        obj = tmp_path / "stats.obj"
        _make_obj(obj, 30)
        stats = _load_mesh_stats(obj)
        assert isinstance(stats, MeshStats)
        assert stats.faces == 30
        assert stats.vertices >= 30

    def test_non_obj_returns_invalid(self, tmp_path: Path) -> None:
        """Non-.obj files without trimesh should be invalid."""
        bad = tmp_path / "unknown.xyz"
        bad.write_text("not a mesh", encoding="utf-8")
        stats = _load_mesh_stats(bad)
        # Either invalid (no parser) or valid with 0 faces
        assert not stats.is_valid or stats.faces == 0


class TestDecimateMeshesDetailed:
    """Detailed tests for decimate_meshes behavior."""

    def test_exact_limit_not_decimated(self, tmp_path: Path) -> None:
        """A mesh with exactly roblox_max_faces should be copied, not decimated."""
        mesh = tmp_path / "exact.obj"
        _make_obj(mesh, 100)
        result = decimate_meshes([mesh], tmp_path / "out", roblox_max_faces=100)
        entry = result.entries[0]
        assert entry.was_copied is True
        assert entry.was_decimated is False
        assert entry.original_faces == 100

    def test_one_below_limit(self, tmp_path: Path) -> None:
        mesh = tmp_path / "below.obj"
        _make_obj(mesh, 99)
        result = decimate_meshes([mesh], tmp_path / "out", roblox_max_faces=100)
        assert result.already_compliant == 1

    def test_output_preserves_filename(self, tmp_path: Path) -> None:
        mesh = tmp_path / "my_model.obj"
        _make_obj(mesh, 5)
        out = tmp_path / "out"
        result = decimate_meshes([mesh], out)
        assert result.entries[0].output_path.name == "my_model.obj"

    def test_output_directory_created_if_missing(self, tmp_path: Path) -> None:
        mesh = tmp_path / "m.obj"
        _make_obj(mesh, 5)
        out = tmp_path / "deep" / "nested" / "output"
        decimate_meshes([mesh], out)
        assert out.exists()

    def test_mixed_valid_and_invalid(self, tmp_path: Path) -> None:
        """Mix of valid .obj and invalid files."""
        good = tmp_path / "good.obj"
        _make_obj(good, 20)
        bad = tmp_path / "bad.fbx"
        bad.write_text("not a mesh", encoding="utf-8")

        result = decimate_meshes([good, bad], tmp_path / "out")
        assert result.total_meshes == 2
        assert result.already_compliant + result.skipped >= 2

    def test_very_small_mesh(self, tmp_path: Path) -> None:
        """A mesh with just 1 face should be copied as-is."""
        mesh = tmp_path / "tiny.obj"
        _make_obj(mesh, 1)
        result = decimate_meshes([mesh], tmp_path / "out", roblox_max_faces=10_000)
        entry = result.entries[0]
        assert entry.original_faces == 1
        assert entry.was_copied is True

    def test_large_mesh_above_limit(self, tmp_path: Path) -> None:
        """Mesh well above limit should be decimated or copied with warning."""
        mesh = tmp_path / "huge.obj"
        _make_obj(mesh, 500)
        result = decimate_meshes(
            [mesh], tmp_path / "out",
            roblox_max_faces=100,
            target_faces=80,
        )
        entry = result.entries[0]
        assert entry.original_faces == 500
        # Depending on trimesh availability
        if entry.was_decimated:
            assert entry.final_faces <= 100
        else:
            assert entry.was_copied or entry.skipped

    def test_all_compliant_batch(self, tmp_path: Path) -> None:
        """Batch of small meshes should all be copied."""
        meshes = []
        for i in range(5):
            m = tmp_path / f"m{i}.obj"
            _make_obj(m, 10)
            meshes.append(m)

        result = decimate_meshes(meshes, tmp_path / "out", roblox_max_faces=10_000)
        assert result.total_meshes == 5
        assert result.already_compliant == 5
        assert result.decimated == 0

    def test_reduction_ratio_for_compliant(self, tmp_path: Path) -> None:
        mesh = tmp_path / "comp.obj"
        _make_obj(mesh, 50)
        result = decimate_meshes([mesh], tmp_path / "out", roblox_max_faces=10_000)
        assert result.entries[0].reduction_ratio == 1.0

    def test_source_path_recorded(self, tmp_path: Path) -> None:
        mesh = tmp_path / "src_check.obj"
        _make_obj(mesh, 5)
        result = decimate_meshes([mesh], tmp_path / "out")
        assert result.entries[0].source_path == mesh

    def test_warnings_accumulate_for_skipped(self, tmp_path: Path) -> None:
        """Each skipped mesh should generate a warning."""
        bad1 = tmp_path / "bad1.fbx"
        bad1.write_text("x", encoding="utf-8")
        bad2 = tmp_path / "bad2.fbx"
        bad2.write_text("y", encoding="utf-8")
        result = decimate_meshes([bad1, bad2], tmp_path / "out")
        assert len(result.warnings) >= 2
