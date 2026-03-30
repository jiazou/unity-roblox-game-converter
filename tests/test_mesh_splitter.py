"""Tests for modules/mesh_splitter.py and multi-material splitting integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

try:
    import trimesh
    HAS_TRIMESH = True
except ImportError:
    HAS_TRIMESH = False

from modules.mesh_splitter import (
    MeshSplitResult,
    SplitMeshEntry,
    split_mesh,
    _extract_geometries,
)


@pytest.mark.skipif(not HAS_TRIMESH, reason="trimesh not installed")
class TestSplitMesh:
    def test_single_material_no_split(self, tmp_path: Path) -> None:
        mesh = trimesh.primitives.Box()
        mesh_path = tmp_path / "cube.obj"
        mesh.export(str(mesh_path))

        result = split_mesh(mesh_path, material_count=1, output_dir=tmp_path / "out")
        assert not result.was_split
        assert result.submeshes == []

    def test_multi_geometry_scene_splits(self, tmp_path: Path) -> None:
        """A Scene with 2 separate geometries splits into 2 submeshes."""
        box = trimesh.primitives.Box()
        sphere = trimesh.primitives.Sphere()
        # Offset sphere so they don't overlap
        sphere.apply_translation([5, 0, 0])
        scene = trimesh.Scene([box, sphere])
        mesh_path = tmp_path / "multi.glb"
        scene.export(str(mesh_path))

        result = split_mesh(mesh_path, material_count=2, output_dir=tmp_path / "out")
        assert result.was_split
        assert len(result.submeshes) == 2
        for entry in result.submeshes:
            assert entry.output_path.exists()
            assert entry.face_count > 0

    def test_material_count_limits_submeshes(self, tmp_path: Path) -> None:
        """If material_count < geometry count, limit to material_count submeshes."""
        meshes = [trimesh.primitives.Box() for _ in range(3)]
        for i, m in enumerate(meshes):
            m.apply_translation([i * 5, 0, 0])
        scene = trimesh.Scene(meshes)
        mesh_path = tmp_path / "three.glb"
        scene.export(str(mesh_path))

        result = split_mesh(mesh_path, material_count=2, output_dir=tmp_path / "out")
        assert len(result.submeshes) <= 2

    def test_zero_material_count_no_split(self, tmp_path: Path) -> None:
        mesh = trimesh.primitives.Box()
        mesh_path = tmp_path / "cube.obj"
        mesh.export(str(mesh_path))

        result = split_mesh(mesh_path, material_count=0, output_dir=tmp_path / "out")
        assert not result.was_split

    def test_nonexistent_mesh(self, tmp_path: Path) -> None:
        result = split_mesh(tmp_path / "missing.obj", material_count=3, output_dir=tmp_path / "out")
        assert not result.was_split
        assert result.error  # should have an error message

    def test_submesh_indices(self, tmp_path: Path) -> None:
        """Each submesh should have a sequential material_index."""
        box = trimesh.primitives.Box()
        sphere = trimesh.primitives.Sphere()
        sphere.apply_translation([5, 0, 0])
        scene = trimesh.Scene([box, sphere])
        mesh_path = tmp_path / "indexed.glb"
        scene.export(str(mesh_path))

        result = split_mesh(mesh_path, material_count=2, output_dir=tmp_path / "out")
        indices = [e.material_index for e in result.submeshes]
        assert indices == [0, 1]


@pytest.mark.skipif(not HAS_TRIMESH, reason="trimesh not installed")
class TestExtractGeometries:
    def test_single_trimesh(self) -> None:
        mesh = trimesh.primitives.Box()
        geoms = _extract_geometries(mesh)
        assert len(geoms) == 1  # single mesh, no split possible without scipy

    def test_scene_with_multiple(self) -> None:
        box = trimesh.primitives.Box()
        sphere = trimesh.primitives.Sphere()
        sphere.apply_translation([10, 0, 0])
        scene = trimesh.Scene([box, sphere])
        geoms = _extract_geometries(scene)
        assert len(geoms) == 2


# ---------------------------------------------------------------------------
# Integration: _try_split_multi_material in conversion_helpers
# ---------------------------------------------------------------------------

@dataclass
class _FakeComp:
    component_type: str
    properties: dict = field(default_factory=dict)


@dataclass
class _FakeNode:
    name: str = "TestMesh"
    components: list[_FakeComp] = field(default_factory=list)
    children: list[Any] = field(default_factory=list)
    position: tuple[float, float, float] = (0, 0, 0)
    rotation: tuple[float, float, float, float] = (0, 0, 0, 1)
    scale: tuple[float, float, float] = (1, 1, 1)
    mesh_guid: str | None = None
    active: bool = True


class TestGetMaterialGuids:
    def test_extracts_resolved_guids(self) -> None:
        from modules.conversion_helpers import _get_material_guids
        from modules.material_mapper import RobloxMaterialDef

        node = _FakeNode(components=[
            _FakeComp("MeshRenderer", {
                "m_Materials": [
                    {"guid": "mat_a"},
                    {"guid": "mat_b"},
                    {"guid": "mat_unknown"},
                ],
            }),
        ])
        defs = {
            "mat_a": RobloxMaterialDef(),
            "mat_b": RobloxMaterialDef(),
        }
        guids = _get_material_guids(node, defs)
        assert guids == ["mat_a", "mat_b"]

    def test_no_renderer(self) -> None:
        from modules.conversion_helpers import _get_material_guids
        node = _FakeNode(components=[_FakeComp("Transform", {})])
        assert _get_material_guids(node, {}) == []

    def test_no_defs(self) -> None:
        from modules.conversion_helpers import _get_material_guids
        node = _FakeNode(components=[
            _FakeComp("MeshRenderer", {"m_Materials": [{"guid": "x"}]}),
        ])
        assert _get_material_guids(node, None) == []


@pytest.mark.skipif(not HAS_TRIMESH, reason="trimesh not installed")
class TestTrySplitMultiMaterial:
    def test_splits_multi_material_mesh(self, tmp_path: Path) -> None:
        from modules.conversion_helpers import _try_split_multi_material
        from modules.material_mapper import RobloxMaterialDef
        from modules.rbxl_writer import RbxPartEntry

        # Create a mesh with 2 separate geometries
        box = trimesh.primitives.Box()
        sphere = trimesh.primitives.Sphere()
        sphere.apply_translation([5, 0, 0])
        scene = trimesh.Scene([box, sphere])
        mesh_path = tmp_path / "multi.glb"
        scene.export(str(mesh_path))

        part = RbxPartEntry(name="TestObj", mesh_id=str(mesh_path))
        node = _FakeNode(
            name="TestObj",
            components=[_FakeComp("MeshRenderer", {
                "m_Materials": [{"guid": "mat0"}, {"guid": "mat1"}],
            })],
        )
        defs = {
            "mat0": RobloxMaterialDef(color_map="tex0.png"),
            "mat1": RobloxMaterialDef(color_map="tex1.png"),
        }

        did_split = _try_split_multi_material(
            part, node, defs, None, tmp_path / "split",
        )
        assert did_split
        assert part.mesh_id is None  # parent becomes grouping Model
        assert len(part.children) == 2
        assert part.children[0].mesh_id is not None
        assert part.children[1].mesh_id is not None
        # Each child should have a different surface appearance
        assert part.children[0].surface_appearance is not None
        assert part.children[1].surface_appearance is not None

    def test_single_material_no_split(self, tmp_path: Path) -> None:
        from modules.conversion_helpers import _try_split_multi_material
        from modules.material_mapper import RobloxMaterialDef
        from modules.rbxl_writer import RbxPartEntry

        mesh = trimesh.primitives.Box()
        mesh_path = tmp_path / "single.obj"
        mesh.export(str(mesh_path))

        part = RbxPartEntry(name="Single", mesh_id=str(mesh_path))
        node = _FakeNode(components=[_FakeComp("MeshRenderer", {
            "m_Materials": [{"guid": "mat0"}],
        })])
        defs = {"mat0": RobloxMaterialDef()}

        did_split = _try_split_multi_material(part, node, defs, None, tmp_path / "split")
        assert not did_split
        assert part.mesh_id is not None  # unchanged

    def test_no_output_dir_no_split(self) -> None:
        from modules.conversion_helpers import _try_split_multi_material
        from modules.rbxl_writer import RbxPartEntry

        part = RbxPartEntry(name="X", mesh_id="/some/mesh.obj")
        node = _FakeNode()
        assert not _try_split_multi_material(part, node, {}, None, None)


class TestSplitInRbxl:
    """Verify that split parts render correctly as a Model with MeshPart children."""

    def test_grouping_node_renders_as_model(self, tmp_path: Path) -> None:
        from modules.rbxl_writer import RbxPartEntry, RbxSurfaceAppearance, write_rbxl

        parent = RbxPartEntry(
            name="MultiMatMesh",
            # No mesh_id — grouping node
            children=[
                RbxPartEntry(
                    name="MultiMatMesh_mat0",
                    mesh_id="sub0.obj",
                    surface_appearance=RbxSurfaceAppearance(color_map="tex0.png"),
                ),
                RbxPartEntry(
                    name="MultiMatMesh_mat1",
                    mesh_id="sub1.obj",
                    surface_appearance=RbxSurfaceAppearance(color_map="tex1.png"),
                ),
            ],
        )

        rbxl = tmp_path / "split_test.rbxl"
        write_rbxl([parent], [], rbxl)
        content = rbxl.read_text()
        assert 'class="Model"' in content
        assert "MultiMatMesh" in content
        assert "MultiMatMesh_mat0" in content
        assert "MultiMatMesh_mat1" in content
        assert content.count('class="MeshPart"') == 2
