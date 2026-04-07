"""Tests for previously untested logic — batch 3.

Covers:
- conversion_helpers: _is_ui_subtree, _is_system_node, populate_component_report
- rbxl_binary_writer: _parse_property, _parse_vector3, _parse_cframe XML parsing
- roblox_uploader: _patch_rbxl_asset_ids_text fallback patching
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import pytest


# ---------------------------------------------------------------------------
# conversion_helpers — node classification
# ---------------------------------------------------------------------------

from modules.scene_parser import SceneNode, ComponentData


def _make_node(
    name: str = "TestNode",
    components: list[tuple[str, dict]] | None = None,
    children: list[SceneNode] | None = None,
) -> SceneNode:
    """Helper to build a SceneNode with components."""
    comps = [
        ComponentData(component_type=ct, file_id=str(i), properties=props)
        for i, (ct, props) in enumerate(components or [])
    ]
    node = SceneNode(
        name=name,
        file_id="1",
        active=True,
        layer=0,
        tag="Untagged",
        components=comps,
        children=children or [],
    )
    return node


class TestIsUiSubtree:
    """Test UI subtree detection."""

    def test_canvas_node_is_ui(self) -> None:
        from modules.conversion_helpers import _is_ui_subtree
        node = _make_node("Canvas", [("Canvas", {})])
        assert _is_ui_subtree(node) is True

    def test_non_canvas_no_children_is_not_ui(self) -> None:
        from modules.conversion_helpers import _is_ui_subtree
        node = _make_node("Empty", [("Transform", {})])
        assert _is_ui_subtree(node) is False

    def test_majority_recttransform_children_is_ui(self) -> None:
        from modules.conversion_helpers import _is_ui_subtree
        children = [
            _make_node("Child1", [("RectTransform", {})]),
            _make_node("Child2", [("RectTransform", {})]),
            _make_node("Child3", [("Transform", {})]),
        ]
        node = _make_node("Panel", [("Transform", {})], children=children)
        # 2/3 > 0.5 → UI subtree
        assert _is_ui_subtree(node) is True

    def test_minority_recttransform_children_is_not_ui(self) -> None:
        from modules.conversion_helpers import _is_ui_subtree
        children = [
            _make_node("Child1", [("RectTransform", {})]),
            _make_node("Child2", [("Transform", {})]),
            _make_node("Child3", [("Transform", {})]),
            _make_node("Child4", [("Transform", {})]),
        ]
        node = _make_node("Group", [("Transform", {})], children=children)
        # 1/4 < 0.5 → NOT UI subtree
        assert _is_ui_subtree(node) is False

    def test_no_children_no_canvas(self) -> None:
        from modules.conversion_helpers import _is_ui_subtree
        node = _make_node("Cube", [("MeshRenderer", {})])
        assert _is_ui_subtree(node) is False


class TestIsSystemNode:
    """Test system node detection."""

    def test_camera_is_system(self) -> None:
        from modules.conversion_helpers import _is_system_node
        node = _make_node("Main Camera", [("Camera", {})])
        assert _is_system_node(node) is True

    def test_light_is_system(self) -> None:
        from modules.conversion_helpers import _is_system_node
        node = _make_node("Directional Light", [("Light", {})])
        assert _is_system_node(node) is True

    def test_eventsystem_is_system(self) -> None:
        from modules.conversion_helpers import _is_system_node
        node = _make_node("EventSystem", [("Transform", {})])
        assert _is_system_node(node) is True

    def test_regular_gameobject_is_not_system(self) -> None:
        from modules.conversion_helpers import _is_system_node
        node = _make_node("Player", [("MeshRenderer", {})])
        assert _is_system_node(node) is False

    def test_node_with_camera_and_mesh(self) -> None:
        """A node with both Camera and MeshRenderer is still a system node."""
        from modules.conversion_helpers import _is_system_node
        node = _make_node("CamObj", [("Camera", {}), ("MeshRenderer", {})])
        assert _is_system_node(node) is True


# ---------------------------------------------------------------------------
# conversion_helpers — populate_component_report
# ---------------------------------------------------------------------------

from modules.conversion_helpers import populate_component_report, ComponentWarning
from modules.report_generator import ConversionReport


class TestPopulateComponentReport:
    """Test component report population."""

    def test_empty_warnings(self) -> None:
        report = ConversionReport()
        populate_component_report([], report)
        assert report.components.dropped == 0
        assert report.components.dropped_by_type == {}

    def test_single_warning(self) -> None:
        report = ConversionReport()
        warnings = [
            ComponentWarning(
                game_object="Player",
                component_type="Animator",
                suggestion="Use AnimatorBridge",
            ),
        ]
        populate_component_report(warnings, report)
        assert report.components.dropped == 1
        assert report.components.dropped_by_type == {"Animator": 1}
        assert len(report.components.dropped_details) == 1
        assert report.components.dropped_details[0]["game_object"] == "Player"

    def test_multiple_same_type(self) -> None:
        report = ConversionReport()
        warnings = [
            ComponentWarning("A", "Animator", "hint"),
            ComponentWarning("B", "Animator", "hint"),
            ComponentWarning("C", "NavMeshAgent", "hint2"),
        ]
        populate_component_report(warnings, report)
        assert report.components.dropped == 3
        assert report.components.dropped_by_type["Animator"] == 2
        assert report.components.dropped_by_type["NavMeshAgent"] == 1

    def test_with_total_components(self) -> None:
        report = ConversionReport()
        warnings = [ComponentWarning("A", "Animator", "hint")]
        populate_component_report(warnings, report, total_components=10)
        assert report.components.total_encountered == 10
        assert report.components.converted == 9
        assert report.components.dropped == 1

    def test_without_total_components(self) -> None:
        report = ConversionReport()
        warnings = [ComponentWarning("A", "Animator", "hint")]
        populate_component_report(warnings, report)
        assert report.components.total_encountered == 1  # defaults to dropped count
        assert report.components.converted == 0

    def test_top_level_warnings_added(self) -> None:
        report = ConversionReport()
        warnings = [
            ComponentWarning("A", "Animator", "Use AnimatorBridge"),
        ]
        populate_component_report(warnings, report)
        assert any("Animator" in w for w in report.warnings)


# ---------------------------------------------------------------------------
# rbxl_binary_writer — XML property parsing
# ---------------------------------------------------------------------------

from modules.rbxl_binary_writer import (
    _parse_property,
    _parse_vector3,
    _parse_cframe,
    _parse_color3,
    _parse_udim2,
    _parse_number_range,
    TYPE_STRING,
    TYPE_BOOL,
    TYPE_INT32,
    TYPE_FLOAT,
    TYPE_VECTOR3,
    TYPE_CFRAME,
    TYPE_COLOR3,
    TYPE_ENUM,
)


class TestParseProperty:
    """Test XML property element parsing."""

    def test_string_property(self) -> None:
        el = ET.fromstring('<string name="Name">Hello</string>')
        result = _parse_property(el)
        assert result == (TYPE_STRING, "Hello")

    def test_string_empty(self) -> None:
        el = ET.fromstring('<string name="Name"></string>')
        result = _parse_property(el)
        assert result == (TYPE_STRING, "")

    def test_bool_true(self) -> None:
        el = ET.fromstring('<bool name="Anchored">true</bool>')
        result = _parse_property(el)
        assert result == (TYPE_BOOL, True)

    def test_bool_false(self) -> None:
        el = ET.fromstring('<bool name="Anchored">false</bool>')
        result = _parse_property(el)
        assert result == (TYPE_BOOL, False)

    def test_int_property(self) -> None:
        el = ET.fromstring('<int name="Count">42</int>')
        result = _parse_property(el)
        assert result == (TYPE_INT32, 42)

    def test_float_property(self) -> None:
        el = ET.fromstring('<float name="Speed">3.14</float>')
        result = _parse_property(el)
        assert result == (TYPE_FLOAT, pytest.approx(3.14))

    def test_vector3_property(self) -> None:
        el = ET.fromstring(
            '<Vector3 name="Position"><X>1</X><Y>2</Y><Z>3</Z></Vector3>'
        )
        result = _parse_property(el)
        assert result is not None
        assert result[0] == TYPE_VECTOR3
        assert result[1] == (1.0, 2.0, 3.0)

    def test_color3_property(self) -> None:
        el = ET.fromstring(
            '<Color3 name="Color"><R>0.5</R><G>0.7</G><B>0.2</B></Color3>'
        )
        result = _parse_property(el)
        assert result is not None
        assert result[0] == TYPE_COLOR3
        assert result[1] == pytest.approx((0.5, 0.7, 0.2))

    def test_token_enum_numeric(self) -> None:
        el = ET.fromstring('<token name="Material">816</token>')
        result = _parse_property(el)
        assert result == (TYPE_ENUM, 816)

    def test_token_enum_name_fallback(self) -> None:
        """Non-numeric token falls back to 0."""
        el = ET.fromstring('<token name="Material">SmoothPlastic</token>')
        result = _parse_property(el)
        assert result == (TYPE_ENUM, 0)

    def test_unknown_tag_returns_none(self) -> None:
        el = ET.fromstring('<CustomType name="foo">bar</CustomType>')
        result = _parse_property(el)
        assert result is None

    def test_content_with_url_child(self) -> None:
        el = ET.fromstring(
            '<Content name="MeshId"><url>rbxassetid://12345</url></Content>'
        )
        result = _parse_property(el)
        assert result == (TYPE_STRING, "rbxassetid://12345")

    def test_content_flat_text(self) -> None:
        el = ET.fromstring('<Content name="TextureId">rbxassetid://999</Content>')
        result = _parse_property(el)
        assert result == (TYPE_STRING, "rbxassetid://999")


class TestParseVector3:
    def test_normal_vector(self) -> None:
        el = ET.fromstring("<Vector3><X>1.5</X><Y>-2.5</Y><Z>0</Z></Vector3>")
        assert _parse_vector3(el) == (1.5, -2.5, 0.0)

    def test_missing_elements_default_zero(self) -> None:
        el = ET.fromstring("<Vector3><X>1</X></Vector3>")
        assert _parse_vector3(el) == (1.0, 0.0, 0.0)


class TestParseCFrame:
    def test_identity_cframe(self) -> None:
        xml = (
            "<CoordinateFrame>"
            "<X>0</X><Y>0</Y><Z>0</Z>"
            "<R00>1</R00><R01>0</R01><R02>0</R02>"
            "<R10>0</R10><R11>1</R11><R12>0</R12>"
            "<R20>0</R20><R21>0</R21><R22>1</R22>"
            "</CoordinateFrame>"
        )
        el = ET.fromstring(xml)
        result = _parse_cframe(el)
        assert len(result) == 12
        assert result[:3] == (0.0, 0.0, 0.0)  # position
        assert result[3:] == (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)  # identity rotation

    def test_defaults_to_identity(self) -> None:
        el = ET.fromstring("<CoordinateFrame><X>5</X><Y>10</Y><Z>15</Z></CoordinateFrame>")
        result = _parse_cframe(el)
        assert result[:3] == (5.0, 10.0, 15.0)
        # Missing rotation elements default to identity
        assert result[3] == 1.0  # R00
        assert result[7] == 1.0  # R11
        assert result[11] == 1.0  # R22


class TestParseNumberRange:
    def test_two_values(self) -> None:
        el = ET.fromstring("<NumberRange>0.5 1.5</NumberRange>")
        assert _parse_number_range(el) == (0.5, 1.5)

    def test_single_value(self) -> None:
        el = ET.fromstring("<NumberRange>3.0</NumberRange>")
        assert _parse_number_range(el) == (3.0, 3.0)

    def test_empty_defaults_zero(self) -> None:
        el = ET.fromstring("<NumberRange></NumberRange>")
        assert _parse_number_range(el) == (0.0, 0.0)


# ---------------------------------------------------------------------------
# roblox_uploader — text fallback patching
# ---------------------------------------------------------------------------

from modules.roblox_uploader import _patch_rbxl_asset_ids_text


class TestPatchRbxlAssetIdsText:
    """Test the text-based fallback patching."""

    def test_patches_full_filename(self, tmp_path: Path) -> None:
        rbxl = tmp_path / "test.rbxl"
        content = '<url>rbxassetid://texture.png</url>'
        rbxl.write_text(content, encoding="utf-8")
        result = _patch_rbxl_asset_ids_text(content, rbxl, {"texture.png": 12345})
        assert result is True
        patched = rbxl.read_text()
        assert "rbxassetid://12345" in patched

    def test_patches_stem_only(self, tmp_path: Path) -> None:
        rbxl = tmp_path / "test.rbxl"
        content = '<url>rbxassetid://texture</url>'
        rbxl.write_text(content, encoding="utf-8")
        result = _patch_rbxl_asset_ids_text(content, rbxl, {"texture.png": 12345})
        assert result is True
        patched = rbxl.read_text()
        assert "rbxassetid://12345" in patched

    def test_no_match_returns_false(self, tmp_path: Path) -> None:
        rbxl = tmp_path / "test.rbxl"
        content = '<url>rbxassetid://other.png</url>'
        result = _patch_rbxl_asset_ids_text(content, rbxl, {"texture.png": 12345})
        assert result is False

    def test_patches_todo_comment(self, tmp_path: Path) -> None:
        rbxl = tmp_path / "test.rbxl"
        content = '-- TODO: upload texture texture.png here'
        rbxl.write_text(content, encoding="utf-8")
        result = _patch_rbxl_asset_ids_text(content, rbxl, {"texture.png": 12345})
        assert result is True
        patched = rbxl.read_text()
        assert "rbxassetid://12345" in patched

    def test_multiple_assets(self, tmp_path: Path) -> None:
        rbxl = tmp_path / "test.rbxl"
        content = (
            '<url>rbxassetid://mesh.fbx</url>\n'
            '<url>rbxassetid://tex.png</url>'
        )
        rbxl.write_text(content, encoding="utf-8")
        result = _patch_rbxl_asset_ids_text(
            content, rbxl,
            {"mesh.fbx": 111, "tex.png": 222},
        )
        assert result is True
        patched = rbxl.read_text()
        assert "rbxassetid://111" in patched
        assert "rbxassetid://222" in patched

    def test_global_replacement_in_luau_string(self, tmp_path: Path) -> None:
        """Demonstrates the known bug: text fallback replaces inside Luau strings.

        This is a known limitation documented in PROBLEMS.md § 3.9.
        The test documents the current behavior, not the desired behavior.
        """
        rbxl = tmp_path / "test.rbxl"
        content = (
            '<ProtectedString name="Source">'
            'local url = "rbxassetid://texture.png"'
            '</ProtectedString>\n'
            '<url>rbxassetid://texture.png</url>'
        )
        rbxl.write_text(content, encoding="utf-8")
        result = _patch_rbxl_asset_ids_text(content, rbxl, {"texture.png": 12345})
        assert result is True
        patched = rbxl.read_text()
        # Known bug: BOTH occurrences are replaced (including the one in the Luau string)
        assert patched.count("rbxassetid://12345") == 2
