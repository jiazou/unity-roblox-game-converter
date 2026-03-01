"""Black-box tests for modules/prefab_parser.py."""

from pathlib import Path

import pytest

from modules.prefab_parser import PrefabLibrary, PrefabTemplate, parse_prefabs


class TestParsePrefabs:
    """Tests for the parse_prefabs() public API."""

    def test_returns_prefab_library(self, unity_project: Path) -> None:
        lib = parse_prefabs(unity_project)
        assert isinstance(lib, PrefabLibrary)

    def test_discovers_prefab(self, unity_project: Path) -> None:
        lib = parse_prefabs(unity_project)
        assert len(lib.prefabs) >= 1

    def test_prefab_name_from_filename(self, unity_project: Path) -> None:
        lib = parse_prefabs(unity_project)
        assert "TestPrefab" in lib.by_name

    def test_prefab_has_root_node(self, unity_project: Path) -> None:
        lib = parse_prefabs(unity_project)
        tmpl = lib.by_name["TestPrefab"]
        assert tmpl.root is not None
        assert tmpl.root.name == "PrefabRoot"

    def test_prefab_hierarchy(self, unity_project: Path) -> None:
        lib = parse_prefabs(unity_project)
        tmpl = lib.by_name["TestPrefab"]
        root = tmpl.root
        assert len(root.children) == 1
        child = root.children[0]
        assert child.name == "ChildMesh"

    def test_prefab_child_position(self, unity_project: Path) -> None:
        lib = parse_prefabs(unity_project)
        tmpl = lib.by_name["TestPrefab"]
        child = tmpl.root.children[0]
        assert child.position == (5.0, 0.0, 0.0)

    def test_prefab_mesh_guid_extracted(self, unity_project: Path) -> None:
        lib = parse_prefabs(unity_project)
        tmpl = lib.by_name["TestPrefab"]
        child = tmpl.root.children[0]
        assert child.mesh_guid == "aaaa1111aaaa1111aaaa1111aaaa1111"

    def test_referenced_material_guids(self, unity_project: Path) -> None:
        lib = parse_prefabs(unity_project)
        assert "bbbb1111bbbb1111bbbb1111bbbb1111" in lib.referenced_material_guids

    def test_referenced_mesh_guids(self, unity_project: Path) -> None:
        lib = parse_prefabs(unity_project)
        assert "aaaa1111aaaa1111aaaa1111aaaa1111" in lib.referenced_mesh_guids

    def test_all_nodes_indexed(self, unity_project: Path) -> None:
        lib = parse_prefabs(unity_project)
        tmpl = lib.by_name["TestPrefab"]
        # Root (1000) + ChildMesh (3000)
        assert len(tmpl.all_nodes) == 2

    def test_components_attached(self, unity_project: Path) -> None:
        lib = parse_prefabs(unity_project)
        tmpl = lib.by_name["TestPrefab"]
        child = tmpl.root.children[0]
        comp_types = {c.component_type for c in child.components}
        assert "MeshFilter" in comp_types
        assert "MeshRenderer" in comp_types

    def test_missing_assets_dir_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="Assets"):
            parse_prefabs(tmp_path / "nonexistent")

    def test_empty_assets_dir(self, tmp_path: Path) -> None:
        project = tmp_path / "EmptyProject"
        (project / "Assets").mkdir(parents=True)
        lib = parse_prefabs(project)
        assert lib.prefabs == []

    def test_prefab_path_stored(self, unity_project: Path) -> None:
        lib = parse_prefabs(unity_project)
        tmpl = lib.by_name["TestPrefab"]
        assert tmpl.prefab_path.name == "TestPrefab.prefab"
        assert tmpl.prefab_path.exists()

    def test_aggregated_guids_match_individual(self, unity_project: Path) -> None:
        lib = parse_prefabs(unity_project)
        # Library-level sets should be union of all template sets
        all_mat = set()
        all_mesh = set()
        for t in lib.prefabs:
            all_mat |= t.referenced_material_guids
            all_mesh |= t.referenced_mesh_guids
        assert lib.referenced_material_guids == all_mat
        assert lib.referenced_mesh_guids == all_mesh
