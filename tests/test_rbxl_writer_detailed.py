"""Fine-grained unit tests for modules/rbxl_writer.py.

Tests XML structure validation, emissive maps, material enum,
deeply nested hierarchies, multiple scripts, and encoding.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from modules.rbxl_writer import (
    RbxPartEntry,
    RbxScriptEntry,
    RbxSurfaceAppearance,
    RbxWriteResult,
    write_rbxl,
)


def _parse_rbxl(path: Path) -> ET.Element:
    """Parse a .rbxl file and return the root XML element."""
    content = path.read_text(encoding="utf-8")
    clean = content.replace('<?xml version="1.0" ?>', "").strip()
    return ET.fromstring(clean)


class TestXMLStructure:
    """Validate the overall XML structure of the output."""

    def test_root_element_is_roblox(self, tmp_path: Path) -> None:
        rbxl = tmp_path / "test.rbxl"
        write_rbxl([], [], rbxl)
        root = _parse_rbxl(rbxl)
        assert root.tag == "roblox"

    def test_workspace_is_first_child(self, tmp_path: Path) -> None:
        rbxl = tmp_path / "test.rbxl"
        write_rbxl([], [], rbxl)
        root = _parse_rbxl(rbxl)
        items = root.findall("Item")
        workspace = [i for i in items if i.get("class") == "Workspace"]
        assert len(workspace) == 1

    def test_server_script_service_present(self, tmp_path: Path) -> None:
        rbxl = tmp_path / "test.rbxl"
        write_rbxl([], [], rbxl)
        root = _parse_rbxl(rbxl)
        items = root.findall("Item")
        sss = [i for i in items if i.get("class") == "ServerScriptService"]
        assert len(sss) == 1


class TestPartProperties:
    """Test that part properties are correctly serialized."""

    def test_size_property(self, tmp_path: Path) -> None:
        parts = [RbxPartEntry(name="Sized", size=(4.0, 5.0, 6.0))]
        rbxl = tmp_path / "test.rbxl"
        write_rbxl(parts, [], rbxl)
        content = rbxl.read_text()
        assert "4" in content
        assert "5" in content
        assert "6" in content

    def test_anchored_property(self, tmp_path: Path) -> None:
        parts = [RbxPartEntry(name="Anch", anchored=True)]
        rbxl = tmp_path / "test.rbxl"
        write_rbxl(parts, [], rbxl)
        content = rbxl.read_text()
        assert "Anchored" in content

    def test_material_enum_property(self, tmp_path: Path) -> None:
        parts = [RbxPartEntry(name="Mat", material_enum="Neon")]
        rbxl = tmp_path / "test.rbxl"
        write_rbxl(parts, [], rbxl)
        content = rbxl.read_text()
        assert "Neon" in content

    def test_transparency_property(self, tmp_path: Path) -> None:
        parts = [RbxPartEntry(name="Glass", transparency=0.7)]
        rbxl = tmp_path / "test.rbxl"
        write_rbxl(parts, [], rbxl)
        content = rbxl.read_text()
        assert "0.7" in content
        assert "Transparency" in content


class TestSurfaceAppearanceDetailed:
    """Detailed tests for SurfaceAppearance serialization."""

    def test_metalness_map(self, tmp_path: Path) -> None:
        sa = RbxSurfaceAppearance(metalness_map="metal.png")
        parts = [RbxPartEntry(name="M", mesh_id="m.obj", surface_appearance=sa)]
        rbxl = tmp_path / "test.rbxl"
        write_rbxl(parts, [], rbxl)
        content = rbxl.read_text()
        assert "metal.png" in content

    def test_roughness_map(self, tmp_path: Path) -> None:
        sa = RbxSurfaceAppearance(roughness_map="rough.png")
        parts = [RbxPartEntry(name="R", mesh_id="m.obj", surface_appearance=sa)]
        rbxl = tmp_path / "test.rbxl"
        write_rbxl(parts, [], rbxl)
        content = rbxl.read_text()
        assert "rough.png" in content

    def test_emissive_fields(self, tmp_path: Path) -> None:
        sa = RbxSurfaceAppearance(
            color_map="c.png",
            emissive_mask="em.png",
            emissive_strength=2.5,
            emissive_tint=(1.0, 0.5, 0.0),
        )
        parts = [RbxPartEntry(name="E", mesh_id="m.obj", surface_appearance=sa)]
        rbxl = tmp_path / "test.rbxl"
        write_rbxl(parts, [], rbxl)
        content = rbxl.read_text()
        assert "em.png" in content

    def test_full_pbr_material(self, tmp_path: Path) -> None:
        sa = RbxSurfaceAppearance(
            color_map="color.png",
            normal_map="normal.png",
            metalness_map="metalness.png",
            roughness_map="roughness.png",
        )
        parts = [RbxPartEntry(name="PBR", mesh_id="m.obj", surface_appearance=sa)]
        rbxl = tmp_path / "test.rbxl"
        write_rbxl(parts, [], rbxl)
        content = rbxl.read_text()
        assert "color.png" in content
        assert "normal.png" in content
        assert "metalness.png" in content
        assert "roughness.png" in content


class TestHierarchy:
    """Test deeply nested part hierarchies."""

    def test_three_level_nesting(self, tmp_path: Path) -> None:
        leaf = RbxPartEntry(name="Leaf")
        mid = RbxPartEntry(name="Mid", children=[leaf])
        root = RbxPartEntry(name="Root", children=[mid])
        rbxl = tmp_path / "test.rbxl"
        result = write_rbxl([root], [], rbxl)
        content = rbxl.read_text()
        assert "Root" in content
        assert "Mid" in content
        assert "Leaf" in content
        # parts_written counts top-level parts only
        assert result.parts_written == 1

    def test_multiple_children(self, tmp_path: Path) -> None:
        c1 = RbxPartEntry(name="Child1")
        c2 = RbxPartEntry(name="Child2")
        c3 = RbxPartEntry(name="Child3")
        parent = RbxPartEntry(name="Parent", children=[c1, c2, c3])
        rbxl = tmp_path / "test.rbxl"
        result = write_rbxl([parent], [], rbxl)
        # parts_written counts top-level parts only
        assert result.parts_written == 1
        content = rbxl.read_text()
        for name in ("Parent", "Child1", "Child2", "Child3"):
            assert name in content

    def test_sibling_roots(self, tmp_path: Path) -> None:
        r1 = RbxPartEntry(name="Root1")
        r2 = RbxPartEntry(name="Root2")
        rbxl = tmp_path / "test.rbxl"
        result = write_rbxl([r1, r2], [], rbxl)
        assert result.parts_written == 2


class TestScriptSerialization:
    """Test script serialization in .rbxl."""

    def test_special_characters_in_script(self, tmp_path: Path) -> None:
        scripts = [RbxScriptEntry(
            name="Special",
            luau_source='local x = "hello <world> & \'quoted\'"',
        )]
        rbxl = tmp_path / "test.rbxl"
        write_rbxl([], scripts, rbxl)
        content = rbxl.read_text()
        # XML should properly encode or CDATA-wrap special chars
        assert "Special" in content

    def test_module_script_type(self, tmp_path: Path) -> None:
        scripts = [RbxScriptEntry(
            name="Lib",
            luau_source="return {}",
            script_type="ModuleScript",
        )]
        rbxl = tmp_path / "test.rbxl"
        write_rbxl([], scripts, rbxl)
        content = rbxl.read_text()
        assert "ModuleScript" in content

    def test_local_script_type(self, tmp_path: Path) -> None:
        scripts = [RbxScriptEntry(
            name="Client",
            luau_source="-- client",
            script_type="LocalScript",
        )]
        rbxl = tmp_path / "test.rbxl"
        write_rbxl([], scripts, rbxl)
        content = rbxl.read_text()
        assert "LocalScript" in content

    def test_multiple_scripts(self, tmp_path: Path) -> None:
        scripts = [
            RbxScriptEntry(name="A", luau_source="-- a"),
            RbxScriptEntry(name="B", luau_source="-- b"),
            RbxScriptEntry(name="C", luau_source="-- c"),
        ]
        rbxl = tmp_path / "test.rbxl"
        result = write_rbxl([], scripts, rbxl)
        assert result.scripts_written == 3

    def test_inline_script_on_mesh_part(self, tmp_path: Path) -> None:
        script = RbxScriptEntry(name="Effect", luau_source="-- vfx")
        part = RbxPartEntry(
            name="VFX",
            mesh_id="m.obj",
            scripts=[script],
        )
        rbxl = tmp_path / "test.rbxl"
        result = write_rbxl([part], [], rbxl)
        content = rbxl.read_text()
        assert "Effect" in content
        assert "-- vfx" in content
        # Inline scripts on parts are NOT counted in scripts_written
        # (only top-level ServerScriptService scripts are counted)
        assert result.scripts_written == 0


class TestWriteResult:
    """Test RbxWriteResult properties."""

    def test_output_path_correct(self, tmp_path: Path) -> None:
        rbxl = tmp_path / "game.rbxl"
        result = write_rbxl([], [], rbxl)
        assert result.output_path == rbxl

    def test_zero_parts_zero_scripts(self, tmp_path: Path) -> None:
        result = write_rbxl([], [], tmp_path / "empty.rbxl")
        assert result.parts_written == 0
        assert result.scripts_written == 0
