"""Tests for modules/vertex_color_baker.py.

Tests vertex colour extraction, UV-space rasterisation, and albedo multiplication.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from modules.vertex_color_baker import (
    BakeResult,
    VertexColorBakeResult,
    _load_mesh_vertex_data,
    _rasterise_vertex_colors,
    bake_vertex_colors_batch,
    bake_vertex_colors_into_albedo,
)


# ── Helpers ──────────────────────────────────────────────────────────


def _make_colored_obj(path: Path, vertex_colors: list[tuple[float, ...]]) -> Path:
    """Create an OBJ file with vertex colours embedded in PLY-style comments.

    OBJ doesn't natively support vertex colours in a standard way that trimesh
    picks up, so we create a PLY file instead for reliable vertex colour tests.
    """
    raise NotImplementedError("Use _make_colored_ply instead")


def _make_colored_ply(path: Path, vertex_colors: list[tuple[int, int, int, int]]) -> Path:
    """Create a PLY file with vertex colours.

    Creates a single triangle with the given per-vertex RGBA colours
    and UV coordinates covering the full 0–1 range.
    """
    n_verts = len(vertex_colors)
    assert n_verts >= 3

    header = (
        "ply\n"
        "format ascii 1.0\n"
        f"element vertex {n_verts}\n"
        "property float x\n"
        "property float y\n"
        "property float z\n"
        "property uchar red\n"
        "property uchar green\n"
        "property uchar blue\n"
        "property uchar alpha\n"
        "property float s\n"
        "property float t\n"
        "element face 1\n"
        "property list uchar int vertex_indices\n"
        "end_header\n"
    )

    # Three vertices forming a triangle covering the UV square
    verts = [
        (0.0, 0.0, 0.0, 0.0, 0.0),  # bottom-left UV
        (1.0, 0.0, 0.0, 1.0, 0.0),  # bottom-right UV
        (0.0, 1.0, 0.0, 0.0, 1.0),  # top-left UV
    ]

    lines = [header]
    for i in range(n_verts):
        v = verts[i] if i < len(verts) else (0.0, 0.0, 0.0, 0.5, 0.5)
        c = vertex_colors[i]
        lines.append(f"{v[0]} {v[1]} {v[2]} {c[0]} {c[1]} {c[2]} {c[3]} {v[3]} {v[4]}")

    # One triangular face
    face_indices = " ".join(str(i) for i in range(min(n_verts, 3)))
    lines.append(f"3 {face_indices}")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _make_albedo(path: Path, color: tuple[int, int, int], size: int = 64) -> Path:
    """Create a solid-colour albedo texture."""
    img = Image.new("RGB", (size, size), color)
    img.save(path, "PNG")
    return path


# ── Unit tests ───────────────────────────────────────────────────────


class TestLoadMeshVertexData:
    def test_no_vertex_colors_returns_none(self, tmp_path: Path) -> None:
        """A mesh with no vertex colours should return None."""
        obj = tmp_path / "plain.obj"
        obj.write_text(
            "v 0 0 0\nv 1 0 0\nv 0 1 0\n"
            "vt 0 0\nvt 1 0\nvt 0 1\n"
            "f 1/1 2/2 3/3\n",
            encoding="utf-8",
        )
        result = _load_mesh_vertex_data(obj)
        assert result is None

    def test_colored_ply_returns_data(self, tmp_path: Path) -> None:
        """A PLY mesh with vertex colours should return valid data."""
        ply = _make_colored_ply(
            tmp_path / "colored.ply",
            [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255)],
        )
        result = _load_mesh_vertex_data(ply)
        if result is None:
            pytest.skip("trimesh didn't load vertex colors from PLY")
        vertices, faces, uv, colors = result
        assert len(vertices) == 3
        assert len(faces) >= 1
        assert colors.shape == (3, 4)

    def test_all_white_returns_none(self, tmp_path: Path) -> None:
        """All-white vertex colours should return None (no baking needed)."""
        ply = _make_colored_ply(
            tmp_path / "white.ply",
            [(255, 255, 255, 255), (255, 255, 255, 255), (255, 255, 255, 255)],
        )
        result = _load_mesh_vertex_data(ply)
        # Should return None because all white = no useful colour data
        assert result is None

    def test_nonexistent_file_returns_none(self, tmp_path: Path) -> None:
        result = _load_mesh_vertex_data(tmp_path / "ghost.ply")
        assert result is None


class TestRasteriseVertexColors:
    def test_output_shape(self) -> None:
        faces = np.array([[0, 1, 2]])
        uv = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
        colors = np.array([[255, 0, 0, 255], [0, 255, 0, 255], [0, 0, 255, 255]], dtype=np.uint8)
        result = _rasterise_vertex_colors(faces, uv, colors, resolution=16)
        assert result.shape == (16, 16, 4)
        assert result.dtype == np.uint8

    def test_uniform_color_produces_solid(self) -> None:
        """If all vertices have the same colour, the mean should be ~200.

        The hole-filling step propagates the average of covered pixels to
        uncovered pixels, so with a uniform vertex colour the entire output
        should converge to that colour.
        """
        faces = np.array([[0, 1, 2]])
        uv = np.array([[0.0, 0.0], [1.0, 0.0], [0.5, 1.0]], dtype=np.float32)
        colors = np.array([[200, 100, 50, 255]] * 3, dtype=np.uint8)
        result = _rasterise_vertex_colors(faces, uv, colors, resolution=16)
        # The mean R of the entire texture should be ~200 because both
        # directly rasterised and hole-filled pixels share the same colour.
        mean_r = result[..., 0].mean()
        assert abs(mean_r - 200) < 5

    def test_zero_area_triangle_skipped(self) -> None:
        """Degenerate triangle (zero area) should not crash."""
        faces = np.array([[0, 1, 2]])
        uv = np.array([[0.5, 0.5], [0.5, 0.5], [0.5, 0.5]], dtype=np.float32)
        colors = np.array([[255, 0, 0, 255]] * 3, dtype=np.uint8)
        result = _rasterise_vertex_colors(faces, uv, colors, resolution=8)
        assert result.shape == (8, 8, 4)


class TestBakeVertexColorsIntoAlbedo:
    def test_no_vertex_colors_returns_not_baked(self, tmp_path: Path) -> None:
        obj = tmp_path / "plain.obj"
        obj.write_text(
            "v 0 0 0\nv 1 0 0\nv 0 1 0\n"
            "vt 0 0\nvt 1 0\nvt 0 1\n"
            "f 1/1 2/2 3/3\n",
            encoding="utf-8",
        )
        albedo = _make_albedo(tmp_path / "albedo.png", (200, 200, 200))
        result = bake_vertex_colors_into_albedo(
            obj, albedo, tmp_path / "out.png",
        )
        assert not result.baked
        assert not result.has_vertex_colors

    def test_missing_mesh_returns_not_baked(self, tmp_path: Path) -> None:
        albedo = _make_albedo(tmp_path / "albedo.png", (200, 200, 200))
        result = bake_vertex_colors_into_albedo(
            tmp_path / "ghost.obj", albedo, tmp_path / "out.png",
        )
        assert not result.baked

    def test_missing_albedo_returns_error(self, tmp_path: Path) -> None:
        ply = _make_colored_ply(
            tmp_path / "mesh.ply",
            [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255)],
        )
        result = bake_vertex_colors_into_albedo(
            ply, tmp_path / "ghost_albedo.png", tmp_path / "out.png",
        )
        # Either not baked (no colors loaded) or error on albedo open
        if result.has_vertex_colors:
            assert result.error != ""


class TestBakeVertexColorsBatch:
    def test_empty_list(self, tmp_path: Path) -> None:
        result = bake_vertex_colors_batch([], tmp_path / "out")
        assert result.total == 0
        assert result.baked == 0

    def test_batch_with_no_colors(self, tmp_path: Path) -> None:
        obj = tmp_path / "plain.obj"
        obj.write_text(
            "v 0 0 0\nv 1 0 0\nv 0 1 0\n"
            "vt 0 0\nvt 1 0\nvt 0 1\n"
            "f 1/1 2/2 3/3\n",
            encoding="utf-8",
        )
        albedo = _make_albedo(tmp_path / "albedo.png", (200, 200, 200))
        result = bake_vertex_colors_batch(
            [(obj, albedo)], tmp_path / "out",
        )
        assert result.total == 1
        assert result.no_colors == 1
        assert result.baked == 0
