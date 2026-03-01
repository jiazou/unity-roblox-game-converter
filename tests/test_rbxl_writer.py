"""Black-box tests for modules/rbxl_writer.py."""

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


class TestWriteRbxl:
    """Tests for the write_rbxl() public API."""

    def test_returns_write_result(self, tmp_path: Path) -> None:
        result = write_rbxl([], [], tmp_path / "test.rbxl")
        assert isinstance(result, RbxWriteResult)

    def test_creates_file(self, tmp_path: Path) -> None:
        rbxl = tmp_path / "output.rbxl"
        write_rbxl([], [], rbxl)
        assert rbxl.exists()
        assert rbxl.stat().st_size > 0

    def test_valid_xml(self, tmp_path: Path) -> None:
        rbxl = tmp_path / "output.rbxl"
        write_rbxl([], [], rbxl)
        content = rbxl.read_text(encoding="utf-8")
        # Should be valid XML
        root = ET.fromstring(content.replace('<?xml version="1.0" ?>', "").strip())
        assert root.tag == "roblox"

    def test_workspace_element_present(self, tmp_path: Path) -> None:
        rbxl = tmp_path / "output.rbxl"
        write_rbxl([], [], rbxl)
        content = rbxl.read_text(encoding="utf-8")
        assert "Workspace" in content

    def test_server_script_service_present(self, tmp_path: Path) -> None:
        rbxl = tmp_path / "output.rbxl"
        write_rbxl([], [], rbxl)
        content = rbxl.read_text(encoding="utf-8")
        assert "ServerScriptService" in content

    def test_parts_written_count(self, tmp_path: Path) -> None:
        parts = [
            RbxPartEntry(name="A"),
            RbxPartEntry(name="B"),
            RbxPartEntry(name="C"),
        ]
        result = write_rbxl(parts, [], tmp_path / "test.rbxl")
        assert result.parts_written == 3

    def test_scripts_written_count(self, tmp_path: Path) -> None:
        scripts = [
            RbxScriptEntry(name="Init", luau_source="print('hello')"),
            RbxScriptEntry(name="Setup", luau_source="-- setup"),
        ]
        result = write_rbxl([], scripts, tmp_path / "test.rbxl")
        assert result.scripts_written == 2

    def test_part_name_in_xml(self, tmp_path: Path) -> None:
        parts = [RbxPartEntry(name="MyCube")]
        rbxl = tmp_path / "test.rbxl"
        write_rbxl(parts, [], rbxl)
        content = rbxl.read_text()
        assert "MyCube" in content

    def test_part_position_in_xml(self, tmp_path: Path) -> None:
        parts = [RbxPartEntry(name="Pos", position=(10.5, 20.0, -5.0))]
        rbxl = tmp_path / "test.rbxl"
        write_rbxl(parts, [], rbxl)
        content = rbxl.read_text()
        assert "10.5" in content
        assert "20.0" in content

    def test_mesh_part_class(self, tmp_path: Path) -> None:
        parts = [RbxPartEntry(name="Mesh", mesh_id="rbxassetid://123")]
        rbxl = tmp_path / "test.rbxl"
        write_rbxl(parts, [], rbxl)
        content = rbxl.read_text()
        assert 'class="MeshPart"' in content

    def test_plain_part_class(self, tmp_path: Path) -> None:
        parts = [RbxPartEntry(name="Box")]  # no mesh_id
        rbxl = tmp_path / "test.rbxl"
        write_rbxl(parts, [], rbxl)
        content = rbxl.read_text()
        assert 'class="Part"' in content

    def test_surface_appearance_on_mesh_part(self, tmp_path: Path) -> None:
        sa = RbxSurfaceAppearance(color_map="tex.png", normal_map="nm.png")
        parts = [RbxPartEntry(name="PBR", mesh_id="/path/mesh.obj", surface_appearance=sa)]
        rbxl = tmp_path / "test.rbxl"
        write_rbxl(parts, [], rbxl)
        content = rbxl.read_text()
        assert "SurfaceAppearance" in content
        assert "tex.png" in content
        assert "nm.png" in content

    def test_surface_appearance_ignored_on_plain_part(self, tmp_path: Path) -> None:
        sa = RbxSurfaceAppearance(color_map="tex.png")
        parts = [RbxPartEntry(name="NoMesh", surface_appearance=sa)]
        rbxl = tmp_path / "test.rbxl"
        write_rbxl(parts, [], rbxl)
        content = rbxl.read_text()
        # SurfaceAppearance should NOT be emitted on a plain Part
        assert "SurfaceAppearance" not in content

    def test_child_parts_nested(self, tmp_path: Path) -> None:
        child = RbxPartEntry(name="ChildPart")
        parent = RbxPartEntry(name="ParentPart", children=[child])
        rbxl = tmp_path / "test.rbxl"
        write_rbxl([parent], [], rbxl)
        content = rbxl.read_text()
        assert "ParentPart" in content
        assert "ChildPart" in content

    def test_transparency_in_xml(self, tmp_path: Path) -> None:
        parts = [RbxPartEntry(name="Glass", transparency=0.5)]
        rbxl = tmp_path / "test.rbxl"
        write_rbxl(parts, [], rbxl)
        content = rbxl.read_text()
        assert "0.5" in content
        assert "Transparency" in content

    def test_color3_in_xml(self, tmp_path: Path) -> None:
        parts = [RbxPartEntry(name="Red", color3=(1.0, 0.0, 0.0))]
        rbxl = tmp_path / "test.rbxl"
        write_rbxl(parts, [], rbxl)
        content = rbxl.read_text()
        assert "Color3" in content

    def test_script_source_in_xml(self, tmp_path: Path) -> None:
        scripts = [RbxScriptEntry(name="Main", luau_source="print('test')")]
        rbxl = tmp_path / "test.rbxl"
        write_rbxl([], scripts, rbxl)
        content = rbxl.read_text()
        assert "print('test')" in content

    def test_empty_parts_valid_output(self, tmp_path: Path) -> None:
        rbxl = tmp_path / "empty.rbxl"
        result = write_rbxl([], [], rbxl)
        assert result.parts_written == 0
        assert result.scripts_written == 0
        assert rbxl.exists()

    def test_output_dir_created(self, tmp_path: Path) -> None:
        rbxl = tmp_path / "subdir" / "deep" / "output.rbxl"
        write_rbxl([], [], rbxl)
        assert rbxl.exists()

    def test_part_with_inline_script(self, tmp_path: Path) -> None:
        script = RbxScriptEntry(name="Effect", luau_source="-- effect")
        part = RbxPartEntry(name="WithScript", scripts=[script])
        rbxl = tmp_path / "test.rbxl"
        write_rbxl([part], [], rbxl)
        content = rbxl.read_text()
        assert "Effect" in content
        assert "-- effect" in content

    def test_alpha_mode_transparency(self, tmp_path: Path) -> None:
        sa = RbxSurfaceAppearance(color_map="t.png", alpha_mode="Transparency")
        parts = [RbxPartEntry(name="T", mesh_id="/m.obj", surface_appearance=sa)]
        rbxl = tmp_path / "test.rbxl"
        write_rbxl(parts, [], rbxl)
        content = rbxl.read_text()
        assert "AlphaMode" in content
