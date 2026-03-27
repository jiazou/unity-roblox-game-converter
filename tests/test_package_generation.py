"""Tests for Roblox package (.rbxm) generation from Unity prefabs.

Covers:
  - write_rbxm() in rbxl_writer.py
  - write_rbxl() ReplicatedStorage/Templates template embedding
  - generate_prefab_packages() in conversion_helpers.py
  - source_prefab_name tracking on SceneNode
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from modules.rbxl_writer import (
    RbxPackageEntry,
    RbxPackageResult,
    RbxPartEntry,
    RbxScriptEntry,
    write_rbxl,
    write_rbxm,
)
from modules.prefab_parser import (
    PrefabComponent,
    PrefabLibrary,
    PrefabNode,
    PrefabTemplate,
)
from modules.conversion_helpers import generate_prefab_packages


# ---------------------------------------------------------------------------
# write_rbxm tests
# ---------------------------------------------------------------------------

class TestWriteRbxm:
    """Tests for the write_rbxm() public API."""

    def test_returns_package_entry(self, tmp_path: Path) -> None:
        result = write_rbxm([], [], tmp_path / "test.rbxm")
        assert isinstance(result, RbxPackageEntry)

    def test_creates_file(self, tmp_path: Path) -> None:
        rbxm = tmp_path / "output.rbxm"
        write_rbxm([], [], rbxm)
        assert rbxm.exists()
        assert rbxm.stat().st_size > 0

    def test_valid_xml(self, tmp_path: Path) -> None:
        rbxm = tmp_path / "output.rbxm"
        write_rbxm([], [], rbxm)
        content = rbxm.read_text(encoding="utf-8")
        root = ET.fromstring(content.replace('<?xml version="1.0" ?>', "").strip())
        assert root.tag == "roblox"

    def test_model_element_present(self, tmp_path: Path) -> None:
        rbxm = tmp_path / "output.rbxm"
        write_rbxm([], [], rbxm)
        content = rbxm.read_text(encoding="utf-8")
        assert 'class="Model"' in content

    def test_no_workspace(self, tmp_path: Path) -> None:
        """Unlike .rbxl, a .rbxm should NOT contain Workspace."""
        rbxm = tmp_path / "output.rbxm"
        write_rbxm([], [], rbxm)
        content = rbxm.read_text(encoding="utf-8")
        assert "Workspace" not in content

    def test_no_server_script_service(self, tmp_path: Path) -> None:
        """Unlike .rbxl, a .rbxm should NOT contain ServerScriptService."""
        rbxm = tmp_path / "output.rbxm"
        write_rbxm([], [], rbxm)
        content = rbxm.read_text(encoding="utf-8")
        assert "ServerScriptService" not in content

    def test_model_name(self, tmp_path: Path) -> None:
        rbxm = tmp_path / "test.rbxm"
        write_rbxm([], [], rbxm, model_name="MyPrefab")
        content = rbxm.read_text(encoding="utf-8")
        assert "MyPrefab" in content

    def test_parts_written_count(self, tmp_path: Path) -> None:
        parts = [
            RbxPartEntry(name="A"),
            RbxPartEntry(name="B"),
        ]
        result = write_rbxm(parts, [], tmp_path / "test.rbxm")
        assert result.parts_written == 2

    def test_scripts_written_count(self, tmp_path: Path) -> None:
        scripts = [
            RbxScriptEntry(name="Init", luau_source="print('hello')"),
        ]
        result = write_rbxm([], scripts, tmp_path / "test.rbxm")
        assert result.scripts_written == 1

    def test_part_name_in_xml(self, tmp_path: Path) -> None:
        parts = [RbxPartEntry(name="MyCube")]
        rbxm = tmp_path / "test.rbxm"
        write_rbxm(parts, [], rbxm)
        content = rbxm.read_text()
        assert "MyCube" in content

    def test_prefab_name_in_result(self, tmp_path: Path) -> None:
        result = write_rbxm([], [], tmp_path / "test.rbxm", model_name="Door")
        assert result.prefab_name == "Door"

    def test_output_path_in_result(self, tmp_path: Path) -> None:
        rbxm = tmp_path / "test.rbxm"
        result = write_rbxm([], [], rbxm)
        assert result.output_path == rbxm

    def test_nested_children(self, tmp_path: Path) -> None:
        child = RbxPartEntry(name="Child")
        parent = RbxPartEntry(name="Parent", children=[child])
        rbxm = tmp_path / "test.rbxm"
        result = write_rbxm([parent], [], rbxm)
        content = rbxm.read_text()
        assert "Parent" in content
        assert "Child" in content
        assert result.parts_written == 2

    def test_output_dir_created(self, tmp_path: Path) -> None:
        rbxm = tmp_path / "subdir" / "deep" / "output.rbxm"
        write_rbxm([], [], rbxm)
        assert rbxm.exists()

    def test_mesh_part_in_model(self, tmp_path: Path) -> None:
        parts = [RbxPartEntry(name="Mesh", mesh_id="rbxassetid://123")]
        rbxm = tmp_path / "test.rbxm"
        write_rbxm(parts, [], rbxm)
        content = rbxm.read_text()
        assert 'class="MeshPart"' in content

    def test_script_inside_model(self, tmp_path: Path) -> None:
        scripts = [RbxScriptEntry(name="Setup", luau_source="-- setup")]
        rbxm = tmp_path / "test.rbxm"
        write_rbxm([], scripts, rbxm)
        content = rbxm.read_text()
        assert "Setup" in content
        assert "-- setup" in content

    def test_empty_model_valid(self, tmp_path: Path) -> None:
        rbxm = tmp_path / "empty.rbxm"
        result = write_rbxm([], [], rbxm)
        assert result.parts_written == 0
        assert result.scripts_written == 0
        assert rbxm.exists()


# ---------------------------------------------------------------------------
# generate_prefab_packages tests
# ---------------------------------------------------------------------------

def _make_prefab(name: str, has_root: bool = True) -> PrefabTemplate:
    """Create a minimal PrefabTemplate for testing."""
    root = None
    if has_root:
        root = PrefabNode(
            name=name,
            file_id="1",
            active=True,
            position=(1.0, 2.0, 3.0),
            rotation=(0.0, 0.0, 0.0, 1.0),
            scale=(1.0, 1.0, 1.0),
        )
    return PrefabTemplate(
        prefab_path=Path(f"/fake/Assets/{name}.prefab"),
        name=name,
        root=root,
    )


def _make_prefab_with_children(name: str) -> PrefabTemplate:
    """Create a PrefabTemplate with a child node."""
    child = PrefabNode(
        name=f"{name}_Child",
        file_id="2",
        active=True,
        position=(0.0, 1.0, 0.0),
        rotation=(0.0, 0.0, 0.0, 1.0),
        scale=(1.0, 1.0, 1.0),
    )
    root = PrefabNode(
        name=name,
        file_id="1",
        active=True,
        position=(0.0, 0.0, 0.0),
        rotation=(0.0, 0.0, 0.0, 1.0),
        scale=(1.0, 1.0, 1.0),
        children=[child],
    )
    return PrefabTemplate(
        prefab_path=Path(f"/fake/Assets/{name}.prefab"),
        name=name,
        root=root,
    )


class TestGeneratePrefabPackages:
    """Tests for generate_prefab_packages()."""

    def test_generates_rbxm_per_prefab(self, tmp_path: Path) -> None:
        lib = PrefabLibrary(prefabs=[
            _make_prefab("Door"),
            _make_prefab("Window"),
        ])
        result = generate_prefab_packages(lib, tmp_path)
        assert result.total_packages == 2
        assert (tmp_path / "packages" / "Door.rbxm").exists()
        assert (tmp_path / "packages" / "Window.rbxm").exists()

    def test_returns_package_result(self, tmp_path: Path) -> None:
        lib = PrefabLibrary(prefabs=[_make_prefab("Box")])
        result = generate_prefab_packages(lib, tmp_path)
        assert isinstance(result, RbxPackageResult)
        assert result.total_packages == 1
        assert len(result.packages) == 1
        assert result.packages[0].prefab_name == "Box"

    def test_empty_library(self, tmp_path: Path) -> None:
        lib = PrefabLibrary()
        result = generate_prefab_packages(lib, tmp_path)
        assert result.total_packages == 0
        assert len(result.packages) == 0

    def test_skips_prefab_without_root(self, tmp_path: Path) -> None:
        lib = PrefabLibrary(prefabs=[_make_prefab("NoRoot", has_root=False)])
        result = generate_prefab_packages(lib, tmp_path)
        assert result.total_packages == 0
        assert len(result.warnings) == 1
        assert "NoRoot" in result.warnings[0]

    def test_packages_dir_created(self, tmp_path: Path) -> None:
        lib = PrefabLibrary(prefabs=[_make_prefab("Tree")])
        generate_prefab_packages(lib, tmp_path)
        assert (tmp_path / "packages").is_dir()

    def test_rbxm_contains_model(self, tmp_path: Path) -> None:
        lib = PrefabLibrary(prefabs=[_make_prefab("Lamp")])
        generate_prefab_packages(lib, tmp_path)
        content = (tmp_path / "packages" / "Lamp.rbxm").read_text(encoding="utf-8")
        assert 'class="Model"' in content
        assert "Lamp" in content

    def test_rbxm_does_not_contain_workspace(self, tmp_path: Path) -> None:
        lib = PrefabLibrary(prefabs=[_make_prefab("Chair")])
        generate_prefab_packages(lib, tmp_path)
        content = (tmp_path / "packages" / "Chair.rbxm").read_text(encoding="utf-8")
        assert "Workspace" not in content

    def test_child_nodes_preserved(self, tmp_path: Path) -> None:
        lib = PrefabLibrary(prefabs=[_make_prefab_with_children("Table")])
        result = generate_prefab_packages(lib, tmp_path)
        assert result.packages[0].parts_written == 2  # root + child
        content = (tmp_path / "packages" / "Table.rbxm").read_text(encoding="utf-8")
        assert "Table_Child" in content

    def test_mixed_valid_and_rootless(self, tmp_path: Path) -> None:
        lib = PrefabLibrary(prefabs=[
            _make_prefab("Valid"),
            _make_prefab("Empty", has_root=False),
            _make_prefab("AlsoValid"),
        ])
        result = generate_prefab_packages(lib, tmp_path)
        assert result.total_packages == 2
        assert len(result.warnings) == 1
        assert (tmp_path / "packages" / "Valid.rbxm").exists()
        assert not (tmp_path / "packages" / "Empty.rbxm").exists()
        assert (tmp_path / "packages" / "AlsoValid.rbxm").exists()

    def test_valid_xml_output(self, tmp_path: Path) -> None:
        lib = PrefabLibrary(prefabs=[_make_prefab("XmlTest")])
        generate_prefab_packages(lib, tmp_path)
        content = (tmp_path / "packages" / "XmlTest.rbxm").read_text(encoding="utf-8")
        root = ET.fromstring(content.replace('<?xml version="1.0" ?>', "").strip())
        assert root.tag == "roblox"
        model_items = root.findall(".//Item[@class='Model']")
        assert len(model_items) == 1

    def test_replicated_templates_populated(self, tmp_path: Path) -> None:
        """generate_prefab_packages should return templates for ReplicatedStorage."""
        lib = PrefabLibrary(prefabs=[
            _make_prefab("EnemyTemplate"),
            _make_prefab("BulletTemplate"),
        ])
        result = generate_prefab_packages(lib, tmp_path)
        assert len(result.replicated_templates) == 2
        names = [name for name, _ in result.replicated_templates]
        assert "EnemyTemplate" in names
        assert "BulletTemplate" in names

    def test_replicated_templates_are_part_entries(self, tmp_path: Path) -> None:
        lib = PrefabLibrary(prefabs=[_make_prefab("Shield")])
        result = generate_prefab_packages(lib, tmp_path)
        assert len(result.replicated_templates) == 1
        name, root_part = result.replicated_templates[0]
        assert name == "Shield"
        assert isinstance(root_part, RbxPartEntry)
        assert root_part.name == "Shield"

    def test_replicated_templates_empty_for_rootless(self, tmp_path: Path) -> None:
        lib = PrefabLibrary(prefabs=[_make_prefab("Broken", has_root=False)])
        result = generate_prefab_packages(lib, tmp_path)
        assert len(result.replicated_templates) == 0


# ---------------------------------------------------------------------------
# write_rbxl template embedding tests (ReplicatedStorage/Templates)
# ---------------------------------------------------------------------------

class TestTemplatesInRbxl:
    """Tests for prefab templates embedded in ReplicatedStorage/Templates inside .rbxl files."""

    def test_templates_not_present_without_templates(self, tmp_path: Path) -> None:
        rbxl = tmp_path / "test.rbxl"
        write_rbxl([], [], rbxl)
        content = rbxl.read_text(encoding="utf-8")
        assert "Templates" not in content

    def test_templates_in_replicated_storage(self, tmp_path: Path) -> None:
        rbxl = tmp_path / "test.rbxl"
        templates = [("Enemy", RbxPartEntry(name="EnemyRoot"))]
        write_rbxl([], [], rbxl, replicated_templates=templates)
        content = rbxl.read_text(encoding="utf-8")
        assert "ReplicatedStorage" in content
        assert "Templates" in content

    def test_model_wraps_template(self, tmp_path: Path) -> None:
        rbxl = tmp_path / "test.rbxl"
        templates = [("Coin", RbxPartEntry(name="CoinGeometry"))]
        write_rbxl([], [], rbxl, replicated_templates=templates)
        content = rbxl.read_text(encoding="utf-8")
        assert 'class="Model"' in content
        assert "Coin" in content
        assert "CoinGeometry" in content

    def test_multiple_templates(self, tmp_path: Path) -> None:
        rbxl = tmp_path / "test.rbxl"
        templates = [
            ("Enemy", RbxPartEntry(name="EnemyBody")),
            ("Bullet", RbxPartEntry(name="BulletMesh")),
            ("Pickup", RbxPartEntry(name="PickupBox")),
        ]
        write_rbxl([], [], rbxl, replicated_templates=templates)
        content = rbxl.read_text(encoding="utf-8")
        assert "Enemy" in content
        assert "Bullet" in content
        assert "Pickup" in content

    def test_template_with_children(self, tmp_path: Path) -> None:
        child = RbxPartEntry(name="Wheel")
        root = RbxPartEntry(name="CarBody", children=[child])
        templates = [("Car", root)]
        rbxl = tmp_path / "test.rbxl"
        write_rbxl([], [], rbxl, replicated_templates=templates)
        content = rbxl.read_text(encoding="utf-8")
        assert "CarBody" in content
        assert "Wheel" in content

    def test_templates_folder_valid_xml(self, tmp_path: Path) -> None:
        templates = [("Box", RbxPartEntry(name="BoxPart"))]
        rbxl = tmp_path / "test.rbxl"
        write_rbxl([], [], rbxl, replicated_templates=templates)
        content = rbxl.read_text(encoding="utf-8")
        root = ET.fromstring(content.replace('<?xml version="1.0" ?>', "").strip())
        rs_items = root.findall(".//Item[@class='ReplicatedStorage']")
        assert len(rs_items) == 1
        folder_items = rs_items[0].findall("Item[@class='Folder']")
        assert len(folder_items) == 1
        model_items = folder_items[0].findall("Item[@class='Model']")
        assert len(model_items) == 1

    def test_workspace_still_present_with_templates(self, tmp_path: Path) -> None:
        """Templates in ReplicatedStorage should coexist with Workspace."""
        templates = [("Tree", RbxPartEntry(name="Trunk"))]
        scene_parts = [RbxPartEntry(name="Ground")]
        rbxl = tmp_path / "test.rbxl"
        write_rbxl(scene_parts, [], rbxl, replicated_templates=templates)
        content = rbxl.read_text(encoding="utf-8")
        assert "Workspace" in content
        assert "ReplicatedStorage" in content
        assert "Ground" in content
        assert "Trunk" in content

    def test_template_mesh_part(self, tmp_path: Path) -> None:
        templates = [("Weapon", RbxPartEntry(name="Sword", mesh_id="rbxassetid://999"))]
        rbxl = tmp_path / "test.rbxl"
        write_rbxl([], [], rbxl, replicated_templates=templates)
        content = rbxl.read_text(encoding="utf-8")
        assert 'class="MeshPart"' in content
        assert "Sword" in content


# ---------------------------------------------------------------------------
# source_prefab_name tracking tests
# ---------------------------------------------------------------------------

class TestSourcePrefabName:
    """Tests for source_prefab_name field on SceneNode."""

    def test_scene_node_has_field(self) -> None:
        from modules.scene_parser import SceneNode
        node = SceneNode(
            name="Test", file_id="1", active=True, layer=0, tag="Untagged",
        )
        assert node.source_prefab_name is None

    def test_field_can_be_set(self) -> None:
        from modules.scene_parser import SceneNode
        node = SceneNode(
            name="Test", file_id="1", active=True, layer=0, tag="Untagged",
            source_prefab_name="MyPrefab",
        )
        assert node.source_prefab_name == "MyPrefab"
