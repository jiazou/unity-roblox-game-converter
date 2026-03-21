"""Black-box tests for modules/mesh_decimator.py."""

from pathlib import Path

import pytest

from modules.mesh_decimator import DecimationResult, decimate_meshes


def _make_obj(path: Path, face_count: int) -> None:
    """Write a minimal .obj file with the given number of triangular faces."""
    lines = []
    # Write enough vertices
    verts_needed = face_count + 2  # triangles sharing vertices
    for i in range(verts_needed):
        lines.append(f"v {float(i)} {float(i % 3)} {float(i % 5)}")
    # Write faces as triangle fan
    for i in range(face_count):
        v1 = 1
        v2 = i + 2
        v3 = i + 3 if i + 3 <= verts_needed else 2
        lines.append(f"f {v1} {v2} {v3}")
    path.write_text("\n".join(lines), encoding="utf-8")


class TestDecimateMeshes:
    """Tests for the decimate_meshes() public API."""

    def test_returns_decimation_result(self, unity_project: Path, tmp_path: Path) -> None:
        mesh = unity_project / "Assets" / "cube.obj"
        result = decimate_meshes([mesh], tmp_path / "meshes_out")
        assert isinstance(result, DecimationResult)

    def test_compliant_mesh_copied(self, unity_project: Path, tmp_path: Path) -> None:
        mesh = unity_project / "Assets" / "cube.obj"
        out = tmp_path / "meshes_out"
        result = decimate_meshes([mesh], out, roblox_max_faces=10_000)
        assert result.total_meshes == 1
        assert result.already_compliant == 1
        assert result.decimated == 0
        assert result.entries[0].was_copied is True
        assert result.entries[0].output_path.exists()

    def test_output_dir_created(self, unity_project: Path, tmp_path: Path) -> None:
        mesh = unity_project / "Assets" / "cube.obj"
        out = tmp_path / "new_dir" / "meshes"
        decimate_meshes([mesh], out)
        assert out.is_dir()

    def test_empty_mesh_list(self, tmp_path: Path) -> None:
        result = decimate_meshes([], tmp_path / "out")
        assert result.total_meshes == 0
        assert result.entries == []

    def test_face_count_detected(self, tmp_path: Path) -> None:
        mesh = tmp_path / "test.obj"
        _make_obj(mesh, 100)
        out = tmp_path / "out"
        result = decimate_meshes([mesh], out, roblox_max_faces=10_000)
        entry = result.entries[0]
        assert entry.original_faces == 100
        assert entry.final_faces == 100
        assert entry.was_copied is True

    def test_mesh_needing_decimation(self, tmp_path: Path) -> None:
        """A mesh with more faces than the limit should be decimated or copied with warning."""
        mesh = tmp_path / "big.obj"
        _make_obj(mesh, 200)
        out = tmp_path / "out"
        result = decimate_meshes(
            [mesh], out,
            roblox_max_faces=50,
            target_faces=40,
        )
        entry = result.entries[0]
        # Either decimated or copied with warning (depends on trimesh availability)
        assert entry.original_faces == 200
        if entry.was_decimated:
            assert result.decimated == 1
        else:
            # trimesh not available — copied unchanged
            assert entry.was_copied or entry.skipped

    def test_multiple_meshes(self, tmp_path: Path) -> None:
        mesh1 = tmp_path / "a.obj"
        mesh2 = tmp_path / "b.obj"
        _make_obj(mesh1, 10)
        _make_obj(mesh2, 20)
        out = tmp_path / "out"
        result = decimate_meshes([mesh1, mesh2], out)
        assert result.total_meshes == 2
        assert len(result.entries) == 2

    def test_invalid_mesh_copied_without_analysis(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.fbx"
        bad.write_text("not a mesh", encoding="utf-8")
        out = tmp_path / "out"
        result = decimate_meshes([bad], out)
        assert result.total_meshes == 1
        assert result.already_compliant == 1
        entry = result.entries[0]
        assert entry.was_copied is True
        assert entry.skipped is False
        assert (out / "bad.fbx").exists()

    def test_reduction_ratio(self, tmp_path: Path) -> None:
        mesh = tmp_path / "compliant.obj"
        _make_obj(mesh, 50)
        out = tmp_path / "out"
        result = decimate_meshes([mesh], out, roblox_max_faces=10_000)
        entry = result.entries[0]
        assert entry.reduction_ratio == 1.0  # no reduction

    def test_output_path_correct(self, tmp_path: Path) -> None:
        mesh = tmp_path / "model.obj"
        _make_obj(mesh, 5)
        out = tmp_path / "out"
        result = decimate_meshes([mesh], out)
        assert result.entries[0].output_path == out / "model.obj"

    def test_source_path_preserved(self, tmp_path: Path) -> None:
        mesh = tmp_path / "src.obj"
        _make_obj(mesh, 5)
        result = decimate_meshes([mesh], tmp_path / "out")
        assert result.entries[0].source_path == mesh

    def test_warnings_for_skip(self, tmp_path: Path) -> None:
        bad = tmp_path / "broken.fbx"
        bad.write_text("garbage", encoding="utf-8")
        result = decimate_meshes([bad], tmp_path / "out")
        assert len(result.warnings) >= 1
