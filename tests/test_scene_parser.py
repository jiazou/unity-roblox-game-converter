"""Black-box tests for modules/scene_parser.py."""

from pathlib import Path

import pytest

from modules.scene_parser import ParsedScene, SceneNode, parse_scene


class TestParseScene:
    """Tests for the parse_scene() public API."""

    def test_returns_parsed_scene(self, unity_project: Path) -> None:
        scene = unity_project / "Assets" / "Main.unity"
        result = parse_scene(scene)
        assert isinstance(result, ParsedScene)
        assert result.scene_path == scene.resolve()

    def test_discovers_game_objects(self, unity_project: Path) -> None:
        scene = unity_project / "Assets" / "Main.unity"
        result = parse_scene(scene)
        assert len(result.all_nodes) == 2  # MainCamera + Cube

    def test_root_nodes(self, unity_project: Path) -> None:
        scene = unity_project / "Assets" / "Main.unity"
        result = parse_scene(scene)
        # MainCamera is root (m_Father: {fileID: 0})
        root_names = [n.name for n in result.roots]
        assert "MainCamera" in root_names

    def test_parent_child_hierarchy(self, unity_project: Path) -> None:
        scene = unity_project / "Assets" / "Main.unity"
        result = parse_scene(scene)
        camera = next(n for n in result.roots if n.name == "MainCamera")
        # Cube should be child of MainCamera
        child_names = [c.name for c in camera.children]
        assert "Cube" in child_names

    def test_transform_position(self, unity_project: Path) -> None:
        scene = unity_project / "Assets" / "Main.unity"
        result = parse_scene(scene)
        cube = result.all_nodes.get("300")
        assert cube is not None
        assert cube.position == (1.0, 2.0, 3.0)

    def test_transform_rotation(self, unity_project: Path) -> None:
        scene = unity_project / "Assets" / "Main.unity"
        result = parse_scene(scene)
        cube = result.all_nodes.get("300")
        assert cube is not None
        assert cube.rotation == (0.0, 0.707, 0.0, 0.707)

    def test_transform_scale(self, unity_project: Path) -> None:
        scene = unity_project / "Assets" / "Main.unity"
        result = parse_scene(scene)
        cube = result.all_nodes.get("300")
        assert cube is not None
        assert cube.scale == (2.0, 2.0, 2.0)

    def test_mesh_guid_extracted(self, unity_project: Path) -> None:
        scene = unity_project / "Assets" / "Main.unity"
        result = parse_scene(scene)
        cube = result.all_nodes.get("300")
        assert cube is not None
        assert cube.mesh_guid == "dddd0000dddd0000dddd0000dddd0001"

    def test_material_guids_extracted(self, unity_project: Path) -> None:
        scene = unity_project / "Assets" / "Main.unity"
        result = parse_scene(scene)
        assert "eeee0000eeee0000eeee0000eeee0001" in result.referenced_material_guids

    def test_mesh_guids_extracted(self, unity_project: Path) -> None:
        scene = unity_project / "Assets" / "Main.unity"
        result = parse_scene(scene)
        assert "dddd0000dddd0000dddd0000dddd0001" in result.referenced_mesh_guids

    def test_components_attached(self, unity_project: Path) -> None:
        scene = unity_project / "Assets" / "Main.unity"
        result = parse_scene(scene)
        cube = result.all_nodes.get("300")
        comp_types = {c.component_type for c in cube.components}
        assert "Transform" in comp_types
        assert "MeshFilter" in comp_types
        assert "MeshRenderer" in comp_types

    def test_game_object_properties(self, unity_project: Path) -> None:
        scene = unity_project / "Assets" / "Main.unity"
        result = parse_scene(scene)
        camera = next(n for n in result.roots if n.name == "MainCamera")
        assert camera.active is True
        assert camera.tag == "MainCamera"
        assert camera.layer == 0

    def test_prefab_instances_recorded(
        self, unity_project_with_prefab_instance: Path
    ) -> None:
        scene = unity_project_with_prefab_instance / "Assets" / "PrefabScene.unity"
        result = parse_scene(scene)
        assert len(result.prefab_instances) == 1
        pi = result.prefab_instances[0]
        assert pi.source_prefab_guid == "ffff0000ffff0000ffff0000ffff0001"
        assert len(pi.modifications) == 3

    def test_missing_scene_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            parse_scene(tmp_path / "nonexistent.unity")

    def test_raw_documents_populated(self, unity_project: Path) -> None:
        scene = unity_project / "Assets" / "Main.unity"
        result = parse_scene(scene)
        assert len(result.raw_documents) > 0

    def test_empty_scene(self, tmp_path: Path) -> None:
        """A scene with just a header and no GameObjects."""
        scene = tmp_path / "empty.unity"
        scene.write_text(
            "%YAML 1.1\n%TAG !u! tag:unity3d.com,2011:\n",
            encoding="utf-8",
        )
        result = parse_scene(scene)
        assert result.roots == []
        assert result.all_nodes == {}
