"""Tests for modules/ui_translator.py.

Covers RectTransform → UDim2 translation, anchor handling,
pivot conversion, hierarchy walking, and warning generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from modules.ui_translator import (
    RobloxUIElement,
    UITranslationResult,
    translate_rect_transform,
    translate_ui_hierarchy,
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
