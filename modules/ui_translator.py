"""
ui_translator.py — Converts Unity RectTransform UI data to Roblox ScreenGui + UDim2.

Unity UI system (Canvas/RectTransform) uses anchor-based positioning:
  - anchorMin / anchorMax  → normalised (0-1) parent-relative corners
  - offsetMin / offsetMax  → pixel offsets from anchor edges
  - pivot                  → normalised origin for position/rotation

Roblox UI uses:
  - ScreenGui              → top-level container (equivalent to Canvas)
  - Frame / TextLabel etc. → child elements positioned via UDim2
  - UDim2.new(xScale, xOffset, yScale, yOffset) → scale + pixel offset
  - AnchorPoint            → normalised pivot (same concept as Unity pivot)

Key difference: Unity Y-axis goes top→bottom, Roblox Y-axis also goes top→bottom
for GUI, so no Y inversion is needed (unlike 3D coordinates).

No other module is imported here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RobloxUIElement:
    """A single Roblox UI element translated from a Unity RectTransform."""
    name: str
    class_name: str = "Frame"  # Frame, TextLabel, TextButton, ImageLabel, etc.

    # Position and size as UDim2 components
    position_x_scale: float = 0.0
    position_x_offset: int = 0
    position_y_scale: float = 0.0
    position_y_offset: int = 0

    size_x_scale: float = 0.0
    size_x_offset: int = 0
    size_y_scale: float = 0.0
    size_y_offset: int = 0

    # AnchorPoint (equivalent to Unity pivot)
    anchor_point_x: float = 0.0
    anchor_point_y: float = 0.0

    children: list["RobloxUIElement"] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class UITranslationResult:
    """Aggregate result of translating Unity UI elements."""
    elements: list[RobloxUIElement] = field(default_factory=list)
    total: int = 0
    converted: int = 0
    warnings: list[str] = field(default_factory=list)


def _safe_float(val: Any, default: float = 0.0) -> float:
    """Safely extract a float from a YAML value."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _extract_vec2(d: dict, key: str) -> tuple[float, float]:
    """Extract a Vector2 (x, y) from a Unity YAML dict."""
    v = d.get(key, {})
    if not isinstance(v, dict):
        return (0.0, 0.0)
    return (_safe_float(v.get("x", 0)), _safe_float(v.get("y", 0)))


def translate_rect_transform(
    properties: dict[str, Any],
    node_name: str = "UIElement",
) -> RobloxUIElement:
    """
    Convert a Unity RectTransform's properties to a Roblox UI element.

    Unity RectTransform properties (from scene YAML):
      m_AnchorMin: {x, y}    — bottom-left anchor (normalised 0-1)
      m_AnchorMax: {x, y}    — top-right anchor (normalised 0-1)
      m_AnchoredPosition: {x, y} — offset from anchored center
      m_SizeDelta: {x, y}    — size adjustment relative to anchors
      m_Pivot: {x, y}        — pivot point (normalised origin)

    Roblox mapping:
      Position = UDim2.new(anchorX_scale, px_offset, anchorY_scale, py_offset)
      Size     = UDim2.new(width_scale, width_offset, height_scale, height_offset)
      AnchorPoint = Vector2(pivot.x, pivot.y)
    """
    anchor_min = _extract_vec2(properties, "m_AnchorMin")
    anchor_max = _extract_vec2(properties, "m_AnchorMax")
    anchored_pos = _extract_vec2(properties, "m_AnchoredPosition")
    size_delta = _extract_vec2(properties, "m_SizeDelta")
    pivot = _extract_vec2(properties, "m_Pivot")

    warnings: list[str] = []

    # Anchors span: how much of the parent this element stretches across
    anchor_width = anchor_max[0] - anchor_min[0]
    anchor_height = anchor_max[1] - anchor_min[1]

    # Size: scale component comes from anchor spread, offset from SizeDelta
    size_x_scale = anchor_width
    size_x_offset = round(size_delta[0])
    size_y_scale = anchor_height
    size_y_offset = round(size_delta[1])

    # Position: anchor center + anchored position offset
    # The anchor center in normalised space:
    anchor_center_x = (anchor_min[0] + anchor_max[0]) / 2.0
    anchor_center_y = (anchor_min[1] + anchor_max[1]) / 2.0

    # Unity Y goes bottom-to-top in RectTransform, Roblox Y goes top-to-bottom.
    # Convert: roblox_y_scale = 1 - unity_y_scale, roblox_y_offset = -unity_y_offset
    pos_x_scale = anchor_center_x
    pos_x_offset = round(anchored_pos[0])
    pos_y_scale = 1.0 - anchor_center_y
    pos_y_offset = round(-anchored_pos[1])

    # Pivot → AnchorPoint (Unity pivot Y is bottom-up, Roblox is top-down)
    anchor_point_x = pivot[0]
    anchor_point_y = 1.0 - pivot[1]

    # Warn about stretched anchors with non-zero SizeDelta (partial stretch)
    if anchor_width > 0 and anchor_width < 1.0 and size_delta[0] != 0:
        warnings.append(
            f"{node_name}: partial horizontal stretch (anchors span "
            f"{anchor_width:.2f}) with SizeDelta.x={size_delta[0]} — "
            f"may not match exactly in Roblox"
        )
    if anchor_height > 0 and anchor_height < 1.0 and size_delta[1] != 0:
        warnings.append(
            f"{node_name}: partial vertical stretch (anchors span "
            f"{anchor_height:.2f}) with SizeDelta.y={size_delta[1]} — "
            f"may not match exactly in Roblox"
        )

    return RobloxUIElement(
        name=node_name,
        position_x_scale=pos_x_scale,
        position_x_offset=pos_x_offset,
        position_y_scale=pos_y_scale,
        position_y_offset=pos_y_offset,
        size_x_scale=size_x_scale,
        size_x_offset=size_x_offset,
        size_y_scale=size_y_scale,
        size_y_offset=size_y_offset,
        anchor_point_x=anchor_point_x,
        anchor_point_y=anchor_point_y,
        warnings=warnings,
    )


def translate_ui_hierarchy(
    scene_nodes: list[Any],
) -> UITranslationResult:
    """
    Walk a list of SceneNode objects and translate all RectTransform-bearing
    nodes into Roblox UI elements.

    Args:
        scene_nodes: List of SceneNode objects (from scene_parser).

    Returns:
        UITranslationResult with converted elements and warnings.
    """
    result = UITranslationResult()

    def _walk(node: Any) -> RobloxUIElement | None:
        rect_comp = None
        for comp in getattr(node, "components", []):
            if comp.component_type == "RectTransform":
                rect_comp = comp
                break

        if rect_comp is None:
            # Not a UI node — recurse into children for nested UI
            for child in getattr(node, "children", []):
                child_elem = _walk(child)
                if child_elem:
                    result.elements.append(child_elem)
            return None

        result.total += 1
        elem = translate_rect_transform(rect_comp.properties, node.name)
        result.converted += 1
        result.warnings.extend(elem.warnings)

        # Recurse into children
        for child in getattr(node, "children", []):
            child_elem = _walk(child)
            if child_elem:
                elem.children.append(child_elem)

        return elem

    for node in scene_nodes:
        elem = _walk(node)
        if elem:
            result.elements.append(elem)

    return result
