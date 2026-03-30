"""Tests for modules/ui_translator.py.

Covers RectTransform → UDim2 translation, anchor handling,
pivot conversion, hierarchy walking, and warning generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from modules.ui_translator import (
    RobloxLayoutChild,
    RobloxUIElement,
    UITranslationResult,
    translate_rect_transform,
    translate_ui_hierarchy,
    to_rbx_ui_element,
    to_rbx_screen_gui,
    _detect_ui_class,
    _extract_layout_groups,
    _extract_text_properties,
    _extract_image_properties,
    _safe_float,
    _extract_vec2,
)


# ---------------------------------------------------------------------------
# Helper to build RectTransform property dicts
# ---------------------------------------------------------------------------

def _rect_props(
    anchor_min: tuple[float, float] = (0.5, 0.5),
    anchor_max: tuple[float, float] = (0.5, 0.5),
    anchored_pos: tuple[float, float] = (0.0, 0.0),
    size_delta: tuple[float, float] = (100.0, 50.0),
    pivot: tuple[float, float] = (0.5, 0.5),
) -> dict[str, Any]:
    return {
        "m_AnchorMin": {"x": anchor_min[0], "y": anchor_min[1]},
        "m_AnchorMax": {"x": anchor_max[0], "y": anchor_max[1]},
        "m_AnchoredPosition": {"x": anchored_pos[0], "y": anchored_pos[1]},
        "m_SizeDelta": {"x": size_delta[0], "y": size_delta[1]},
        "m_Pivot": {"x": pivot[0], "y": pivot[1]},
    }


# Lightweight fake SceneNode/ComponentData for hierarchy tests
@dataclass
class _FakeComp:
    component_type: str
    properties: dict = field(default_factory=dict)

@dataclass
class _FakeNode:
    name: str = "UINode"
    components: list[_FakeComp] = field(default_factory=list)
    children: list["_FakeNode"] = field(default_factory=list)


# ---------------------------------------------------------------------------
# _safe_float / _extract_vec2
# ---------------------------------------------------------------------------

class TestSafeFloat:
    def test_normal(self) -> None:
        assert _safe_float(3.14) == pytest.approx(3.14)

    def test_none(self) -> None:
        assert _safe_float(None) == 0.0

    def test_none_with_default(self) -> None:
        assert _safe_float(None, 5.0) == 5.0

    def test_invalid_string(self) -> None:
        assert _safe_float("abc") == 0.0

    def test_string_number(self) -> None:
        assert _safe_float("42") == 42.0


class TestExtractVec2:
    def test_normal(self) -> None:
        d = {"pos": {"x": 10.0, "y": 20.0}}
        assert _extract_vec2(d, "pos") == (10.0, 20.0)

    def test_missing_key(self) -> None:
        assert _extract_vec2({}, "pos") == (0.0, 0.0)

    def test_non_dict_value(self) -> None:
        assert _extract_vec2({"pos": "invalid"}, "pos") == (0.0, 0.0)


# ---------------------------------------------------------------------------
# translate_rect_transform
# ---------------------------------------------------------------------------

class TestTranslateRectTransform:
    def test_centered_element(self) -> None:
        """Anchors at center (0.5, 0.5) with no offset → centered position."""
        props = _rect_props()
        elem = translate_rect_transform(props, "CenterBtn")
        assert elem.name == "CenterBtn"
        assert elem.position_x_scale == pytest.approx(0.5)
        # Unity Y center 0.5 → Roblox Y = 1 - 0.5 = 0.5
        assert elem.position_y_scale == pytest.approx(0.5)
        assert elem.size_x_offset == 100
        assert elem.size_y_offset == 50

    def test_full_stretch(self) -> None:
        """Anchors spanning full parent (0,0)→(1,1) → size scale = 1."""
        props = _rect_props(
            anchor_min=(0.0, 0.0),
            anchor_max=(1.0, 1.0),
            size_delta=(0.0, 0.0),
        )
        elem = translate_rect_transform(props)
        assert elem.size_x_scale == pytest.approx(1.0)
        assert elem.size_y_scale == pytest.approx(1.0)
        assert elem.size_x_offset == 0
        assert elem.size_y_offset == 0

    def test_top_left_anchor(self) -> None:
        """Anchors at top-left corner (0, 1)."""
        props = _rect_props(
            anchor_min=(0.0, 1.0),
            anchor_max=(0.0, 1.0),
            size_delta=(200.0, 100.0),
        )
        elem = translate_rect_transform(props)
        assert elem.position_x_scale == pytest.approx(0.0)
        # Unity Y=1 (top) → Roblox Y = 1 - 1 = 0 (top)
        assert elem.position_y_scale == pytest.approx(0.0)

    def test_bottom_right_anchor(self) -> None:
        """Anchors at bottom-right corner (1, 0)."""
        props = _rect_props(
            anchor_min=(1.0, 0.0),
            anchor_max=(1.0, 0.0),
        )
        elem = translate_rect_transform(props)
        assert elem.position_x_scale == pytest.approx(1.0)
        # Unity Y=0 (bottom) → Roblox Y = 1 - 0 = 1 (bottom)
        assert elem.position_y_scale == pytest.approx(1.0)

    def test_custom_pivot(self) -> None:
        """Custom pivot (0.0, 1.0) → AnchorPoint (0.0, 0.0)."""
        props = _rect_props(pivot=(0.0, 1.0))
        elem = translate_rect_transform(props)
        assert elem.anchor_point_x == pytest.approx(0.0)
        # Unity pivot Y=1 → Roblox AnchorPoint Y = 1 - 1 = 0
        assert elem.anchor_point_y == pytest.approx(0.0)

    def test_offset_from_anchor(self) -> None:
        """AnchoredPosition offset is applied correctly."""
        props = _rect_props(
            anchored_pos=(50.0, -30.0),
        )
        elem = translate_rect_transform(props)
        assert elem.position_x_offset == 50
        # Unity Y offset -30 → Roblox Y offset = -(-30) = 30
        assert elem.position_y_offset == 30

    def test_partial_horizontal_stretch_warns(self) -> None:
        """Partial horizontal stretch with non-zero SizeDelta.x → warning."""
        props = _rect_props(
            anchor_min=(0.0, 0.5),
            anchor_max=(0.5, 0.5),
            size_delta=(20.0, 50.0),
        )
        elem = translate_rect_transform(props, "PartialH")
        assert len(elem.warnings) >= 1
        assert "horizontal" in elem.warnings[0].lower()

    def test_partial_vertical_stretch_warns(self) -> None:
        """Partial vertical stretch with non-zero SizeDelta.y → warning."""
        props = _rect_props(
            anchor_min=(0.5, 0.2),
            anchor_max=(0.5, 0.8),
            size_delta=(100.0, 10.0),
        )
        elem = translate_rect_transform(props, "PartialV")
        assert len(elem.warnings) >= 1
        assert "vertical" in elem.warnings[0].lower()

    def test_no_warning_for_zero_sizedelta(self) -> None:
        """Partial stretch with SizeDelta.x=0 → no warning."""
        props = _rect_props(
            anchor_min=(0.0, 0.5),
            anchor_max=(0.5, 0.5),
            size_delta=(0.0, 50.0),
        )
        elem = translate_rect_transform(props)
        # No horizontal warning since SizeDelta.x == 0
        horiz_warnings = [w for w in elem.warnings if "horizontal" in w.lower()]
        assert len(horiz_warnings) == 0

    def test_empty_properties(self) -> None:
        """Missing properties default to zero/default values."""
        elem = translate_rect_transform({})
        assert elem.position_x_scale == pytest.approx(0.0)
        assert elem.size_x_scale == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# translate_ui_hierarchy
# ---------------------------------------------------------------------------

class TestTranslateUIHierarchy:
    def test_empty_hierarchy(self) -> None:
        result = translate_ui_hierarchy([])
        assert result.total == 0
        assert result.converted == 0
        assert result.elements == []

    def test_single_ui_node(self) -> None:
        node = _FakeNode(
            name="Panel",
            components=[_FakeComp("RectTransform", _rect_props())],
        )
        result = translate_ui_hierarchy([node])
        assert result.total == 1
        assert result.converted == 1
        assert len(result.elements) == 1
        assert result.elements[0].name == "Panel"

    def test_nested_ui_nodes(self) -> None:
        child = _FakeNode(
            name="Button",
            components=[_FakeComp("RectTransform", _rect_props())],
        )
        parent = _FakeNode(
            name="Panel",
            components=[_FakeComp("RectTransform", _rect_props())],
            children=[child],
        )
        result = translate_ui_hierarchy([parent])
        assert result.total == 2
        assert result.converted == 2
        assert len(result.elements) == 1  # only root
        assert len(result.elements[0].children) == 1
        assert result.elements[0].children[0].name == "Button"

    def test_mixed_ui_and_3d_nodes(self) -> None:
        """Non-UI node (Transform only) with UI child → child promoted to root."""
        ui_child = _FakeNode(
            name="HUD",
            components=[_FakeComp("RectTransform", _rect_props())],
        )
        non_ui_parent = _FakeNode(
            name="Camera",
            components=[_FakeComp("Transform", {})],
            children=[ui_child],
        )
        result = translate_ui_hierarchy([non_ui_parent])
        assert result.total == 1
        assert result.converted == 1
        # The UI child should be promoted to result.elements
        assert len(result.elements) == 1
        assert result.elements[0].name == "HUD"

    def test_warnings_aggregated(self) -> None:
        """Warnings from individual elements are collected in the result."""
        node = _FakeNode(
            name="Stretched",
            components=[_FakeComp("RectTransform", _rect_props(
                anchor_min=(0.0, 0.5),
                anchor_max=(0.5, 0.5),
                size_delta=(20.0, 50.0),
            ))],
        )
        result = translate_ui_hierarchy([node])
        assert len(result.warnings) >= 1


# ---------------------------------------------------------------------------
# UI component type detection
# ---------------------------------------------------------------------------

class TestDetectUIClass:
    def test_text_detected_as_text_label(self) -> None:
        comps = [_FakeComp("Text", {})]
        assert _detect_ui_class(comps) == "TextLabel"

    def test_button_detected_as_text_button(self) -> None:
        comps = [_FakeComp("Button", {})]
        assert _detect_ui_class(comps) == "TextButton"

    def test_image_detected_as_image_label(self) -> None:
        comps = [_FakeComp("Image", {})]
        assert _detect_ui_class(comps) == "ImageLabel"

    def test_no_ui_component_defaults_to_frame(self) -> None:
        comps = [_FakeComp("RectTransform", {})]
        assert _detect_ui_class(comps) == "Frame"

    def test_qualified_name_detected(self) -> None:
        comps = [_FakeComp("UnityEngine.UI.Text", {})]
        assert _detect_ui_class(comps) == "TextLabel"


class TestExtractTextProperties:
    def test_extracts_text_and_size(self) -> None:
        comps = [_FakeComp("Text", {
            "m_Text": "Hello World",
            "m_FontSize": 24,
            "m_Color": {"r": 1, "g": 0, "b": 0, "a": 1},
            "m_Alignment": 4,  # MiddleCenter
        })]
        props = _extract_text_properties(comps)
        assert props["text"] == "Hello World"
        assert props["text_size"] == 24
        assert props["text_color"] == (1.0, 0.0, 0.0)
        assert props["text_x_alignment"] == "Center"
        assert props["text_y_alignment"] == "Center"

    def test_left_alignment(self) -> None:
        comps = [_FakeComp("Text", {"m_Alignment": 0})]  # UpperLeft
        props = _extract_text_properties(comps)
        assert props["text_x_alignment"] == "Left"
        assert props["text_y_alignment"] == "Top"

    def test_no_text_component_returns_empty(self) -> None:
        comps = [_FakeComp("Image", {})]
        assert _extract_text_properties(comps) == {}


class TestExtractImageProperties:
    def test_extracts_image_color(self) -> None:
        comps = [_FakeComp("Image", {
            "m_Color": {"r": 0.5, "g": 0.8, "b": 1.0, "a": 0.7},
        })]
        props = _extract_image_properties(comps)
        assert props["image_color"] == pytest.approx((0.5, 0.8, 1.0))
        assert props["image_transparency"] == pytest.approx(0.3)

    def test_sprite_guid_converted(self) -> None:
        comps = [_FakeComp("Image", {
            "m_Sprite": {"guid": "abc123def456"},
            "m_Color": {"r": 1, "g": 1, "b": 1, "a": 1},
        })]
        props = _extract_image_properties(comps)
        assert "abc123def456" in props.get("image", "")


class TestHierarchyWithUITypes:
    def test_text_node_classified(self) -> None:
        node = _FakeNode(
            name="Score",
            components=[
                _FakeComp("RectTransform", _rect_props()),
                _FakeComp("Text", {"m_Text": "0", "m_FontSize": 32}),
            ],
        )
        result = translate_ui_hierarchy([node])
        assert result.elements[0].class_name == "TextLabel"
        assert result.elements[0].text == "0"
        assert result.elements[0].text_size == 32

    def test_image_node_classified(self) -> None:
        node = _FakeNode(
            name="Icon",
            components=[
                _FakeComp("RectTransform", _rect_props()),
                _FakeComp("Image", {
                    "m_Color": {"r": 1, "g": 0.5, "b": 0, "a": 1},
                }),
            ],
        )
        result = translate_ui_hierarchy([node])
        assert result.elements[0].class_name == "ImageLabel"

    def test_button_node_classified(self) -> None:
        node = _FakeNode(
            name="PlayBtn",
            components=[
                _FakeComp("RectTransform", _rect_props()),
                _FakeComp("Button", {}),
                _FakeComp("Text", {"m_Text": "Play", "m_FontSize": 20}),
            ],
        )
        result = translate_ui_hierarchy([node])
        assert result.elements[0].class_name == "TextButton"
        assert result.elements[0].text == "Play"


class TestToRbxConversion:
    def test_to_rbx_ui_element(self) -> None:
        elem = RobloxUIElement(
            name="TestLabel",
            class_name="TextLabel",
            position_x_scale=0.5,
            position_y_scale=0.5,
            size_x_offset=200,
            size_y_offset=50,
            text="Hello",
            text_size=18,
        )
        rbx = to_rbx_ui_element(elem)
        assert rbx.name == "TestLabel"
        assert rbx.class_name == "TextLabel"
        assert rbx.text == "Hello"
        assert rbx.text_size == 18

    def test_to_rbx_screen_gui(self) -> None:
        elem = RobloxUIElement(name="Panel")
        gui = to_rbx_screen_gui("GameUI", [elem])
        assert gui.name == "GameUI"
        assert len(gui.elements) == 1

    def test_children_converted(self) -> None:
        child = RobloxUIElement(name="Child", class_name="TextLabel", text="Hi")
        parent = RobloxUIElement(name="Parent", children=[child])
        rbx = to_rbx_ui_element(parent)
        assert len(rbx.children) == 1
        assert rbx.children[0].text == "Hi"


class TestScreenGuiInRbxl:
    def test_screen_gui_written(self, tmp_path) -> None:
        from modules.rbxl_writer import RbxUIElement, RbxScreenGui, write_rbxl

        gui = RbxScreenGui(
            name="HUD",
            elements=[
                RbxUIElement(
                    name="ScoreLabel",
                    class_name="TextLabel",
                    position_x_scale=0.5,
                    position_y_scale=0.0,
                    size_x_offset=200,
                    size_y_offset=50,
                    text="Score: 0",
                    text_size=24,
                ),
            ],
        )
        rbxl = tmp_path / "ui_test.rbxl"
        result = write_rbxl([], [], rbxl, screen_guis=[gui])
        content = rbxl.read_text()
        assert "StarterGui" in content
        assert "ScreenGui" in content
        assert "ScoreLabel" in content
        assert "TextLabel" in content
        assert "Score: 0" in content
        assert result.ui_elements_written == 1

    def test_nested_ui_elements(self, tmp_path) -> None:
        from modules.rbxl_writer import RbxUIElement, RbxScreenGui, write_rbxl

        gui = RbxScreenGui(
            name="Menu",
            elements=[
                RbxUIElement(
                    name="Panel",
                    class_name="Frame",
                    children=[
                        RbxUIElement(name="Title", class_name="TextLabel", text="Game"),
                        RbxUIElement(name="Icon", class_name="ImageLabel", image="rbxassetid://123"),
                    ],
                ),
            ],
        )
        rbxl = tmp_path / "nested_ui.rbxl"
        result = write_rbxl([], [], rbxl, screen_guis=[gui])
        content = rbxl.read_text()
        assert "Panel" in content
        assert "Title" in content
        assert "Icon" in content
        assert result.ui_elements_written == 3  # Panel + Title + Icon


# ---------------------------------------------------------------------------
# Layout group extraction  (MB-3)
# ---------------------------------------------------------------------------


class TestExtractLayoutGroups:
    def test_horizontal_layout_group(self) -> None:
        comps = [_FakeComp("HorizontalLayoutGroup", {
            "m_Spacing": 10,
            "m_ChildAlignment": 4,  # MiddleCenter
        })]
        layouts = _extract_layout_groups(comps)
        assert len(layouts) == 1
        lc = layouts[0]
        assert lc.class_name == "UIListLayout"
        assert lc.fill_direction == "Horizontal"
        assert lc.padding_x_offset == 10
        assert lc.horizontal_alignment == "Center"
        assert lc.vertical_alignment == "Center"

    def test_vertical_layout_group(self) -> None:
        comps = [_FakeComp("VerticalLayoutGroup", {
            "m_Spacing": 5,
            "m_ChildAlignment": 0,  # UpperLeft
        })]
        layouts = _extract_layout_groups(comps)
        assert len(layouts) == 1
        lc = layouts[0]
        assert lc.class_name == "UIListLayout"
        assert lc.fill_direction == "Vertical"
        assert lc.padding_x_offset == 5
        assert lc.horizontal_alignment == "Left"
        assert lc.vertical_alignment == "Top"

    def test_grid_layout_group(self) -> None:
        comps = [_FakeComp("GridLayoutGroup", {
            "m_CellSize": {"x": 80, "y": 60},
            "m_Spacing": {"x": 4, "y": 8},
            "m_ChildAlignment": 1,  # UpperCenter
        })]
        layouts = _extract_layout_groups(comps)
        assert len(layouts) == 1
        lc = layouts[0]
        assert lc.class_name == "UIGridLayout"
        assert lc.cell_size_x_offset == 80
        assert lc.cell_size_y_offset == 60
        assert lc.cell_padding_x_offset == 4
        assert lc.cell_padding_y_offset == 8
        assert lc.horizontal_alignment == "Center"
        assert lc.vertical_alignment == "Top"

    def test_qualified_type_name(self) -> None:
        comps = [_FakeComp("UnityEngine.UI.VerticalLayoutGroup", {
            "m_Spacing": 3,
        })]
        layouts = _extract_layout_groups(comps)
        assert len(layouts) == 1
        assert layouts[0].fill_direction == "Vertical"

    def test_no_layout_group(self) -> None:
        comps = [_FakeComp("RectTransform", {}), _FakeComp("Image", {})]
        layouts = _extract_layout_groups(comps)
        assert layouts == []

    def test_grid_spacing_scalar_fallback(self) -> None:
        """When m_Spacing is a scalar instead of {x, y}, use it for both axes."""
        comps = [_FakeComp("GridLayoutGroup", {
            "m_CellSize": {"x": 50, "y": 50},
            "m_Spacing": 6,
        })]
        layouts = _extract_layout_groups(comps)
        lc = layouts[0]
        assert lc.cell_padding_x_offset == 6
        assert lc.cell_padding_y_offset == 6


class TestLayoutGroupInHierarchy:
    def test_layout_children_populated_in_hierarchy(self) -> None:
        """translate_ui_hierarchy should populate layout_children."""
        node = _FakeNode(
            name="VBox",
            components=[
                _FakeComp("RectTransform", _rect_props()),
                _FakeComp("VerticalLayoutGroup", {"m_Spacing": 8}),
            ],
        )
        result = translate_ui_hierarchy([node])
        elem = result.elements[0]
        assert len(elem.layout_children) == 1
        assert elem.layout_children[0].class_name == "UIListLayout"
        assert elem.layout_children[0].fill_direction == "Vertical"


class TestLayoutGroupToRbx:
    def test_layout_children_converted_to_dicts(self) -> None:
        """to_rbx_ui_element should convert RobloxLayoutChild → dict."""
        elem = RobloxUIElement(
            name="HBox",
            layout_children=[
                RobloxLayoutChild(
                    class_name="UIListLayout",
                    fill_direction="Horizontal",
                    padding_x_offset=12,
                    horizontal_alignment="Center",
                    vertical_alignment="Top",
                ),
            ],
        )
        rbx = to_rbx_ui_element(elem)
        assert len(rbx.layout_children) == 1
        lc = rbx.layout_children[0]
        assert isinstance(lc, dict)
        assert lc["class_name"] == "UIListLayout"
        assert lc["fill_direction"] == "Horizontal"
        assert lc["padding_x_offset"] == 12
        assert lc["horizontal_alignment"] == "Center"

    def test_grid_layout_converted_to_dict(self) -> None:
        elem = RobloxUIElement(
            name="Grid",
            layout_children=[
                RobloxLayoutChild(
                    class_name="UIGridLayout",
                    cell_size_x_offset=64,
                    cell_size_y_offset=64,
                    cell_padding_x_offset=4,
                    cell_padding_y_offset=4,
                ),
            ],
        )
        rbx = to_rbx_ui_element(elem)
        lc = rbx.layout_children[0]
        assert lc["class_name"] == "UIGridLayout"
        assert lc["cell_size_x_offset"] == 64
        assert lc["cell_padding_x_offset"] == 4


class TestLayoutGroupInRbxl:
    def test_list_layout_written_to_rbxl(self, tmp_path) -> None:
        from modules.rbxl_writer import RbxUIElement, RbxScreenGui, write_rbxl

        gui = RbxScreenGui(
            name="LayoutTest",
            elements=[
                RbxUIElement(
                    name="VBox",
                    class_name="Frame",
                    layout_children=[{
                        "class_name": "UIListLayout",
                        "fill_direction": "Vertical",
                        "padding_x_scale": 0.0,
                        "padding_x_offset": 8,
                        "sort_order": "LayoutOrder",
                        "horizontal_alignment": "Left",
                        "vertical_alignment": "Top",
                    }],
                ),
            ],
        )
        rbxl = tmp_path / "layout_test.rbxl"
        write_rbxl([], [], rbxl, screen_guis=[gui])
        content = rbxl.read_text()
        assert "UIListLayout" in content
        assert "FillDirection" in content
        assert "Padding" in content

    def test_grid_layout_written_to_rbxl(self, tmp_path) -> None:
        from modules.rbxl_writer import RbxUIElement, RbxScreenGui, write_rbxl

        gui = RbxScreenGui(
            name="GridTest",
            elements=[
                RbxUIElement(
                    name="Grid",
                    class_name="Frame",
                    layout_children=[{
                        "class_name": "UIGridLayout",
                        "cell_size_x_scale": 0.0,
                        "cell_size_x_offset": 100,
                        "cell_size_y_scale": 0.0,
                        "cell_size_y_offset": 100,
                        "cell_padding_x_scale": 0.0,
                        "cell_padding_x_offset": 5,
                        "cell_padding_y_scale": 0.0,
                        "cell_padding_y_offset": 5,
                        "sort_order": "LayoutOrder",
                        "horizontal_alignment": "Center",
                        "vertical_alignment": "Top",
                    }],
                ),
            ],
        )
        rbxl = tmp_path / "grid_test.rbxl"
        write_rbxl([], [], rbxl, screen_guis=[gui])
        content = rbxl.read_text()
        assert "UIGridLayout" in content
        assert "CellSize" in content
        assert "CellPadding" in content
