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

    # Text properties
    text: str = ""
    text_color: tuple[float, float, float] = (0.0, 0.0, 0.0)
    text_size: int = 14
    font: str = "SourceSans"
    text_x_alignment: str = "Center"
    text_y_alignment: str = "Center"

    # Image properties
    image: str = ""
    image_color: tuple[float, float, float] = (1.0, 1.0, 1.0)
    image_transparency: float = 0.0

    # Appearance
    background_color: tuple[float, float, float] = (1.0, 1.0, 1.0)
    background_transparency: float = 0.0

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


# Unity UI component type names (from MonoBehaviour script references)
# These are detected via component_type matching in scene_parser output
_UI_TYPE_MAP: dict[str, str] = {
    "Text": "TextLabel",
    "UnityEngine.UI.Text": "TextLabel",
    "Button": "TextButton",
    "UnityEngine.UI.Button": "TextButton",
    "Image": "ImageLabel",
    "UnityEngine.UI.Image": "ImageLabel",
    "RawImage": "ImageLabel",
    "UnityEngine.UI.RawImage": "ImageLabel",
    "Canvas": "ScreenGui",
    "UnityEngine.Canvas": "ScreenGui",
    "InputField": "TextBox",
    "UnityEngine.UI.InputField": "TextBox",
    "ScrollRect": "ScrollingFrame",
    "UnityEngine.UI.ScrollRect": "ScrollingFrame",
    "Slider": "Frame",
    "UnityEngine.UI.Slider": "Frame",
    "Toggle": "Frame",
    "UnityEngine.UI.Toggle": "Frame",
}

# Unity font style → Roblox font mapping (approximate)
_FONT_MAP: dict[str, str] = {
    "Arial": "Arial",
    "Arial-Bold": "ArialBold",
    "Roboto": "Roboto",
    "Roboto-Bold": "RobotoBold",
}

# Unity TextAnchor → Roblox alignment
_TEXT_ANCHOR_X: dict[int, str] = {
    0: "Left", 1: "Center", 2: "Right",     # upper-left, upper-center, upper-right
    3: "Left", 4: "Center", 5: "Right",     # middle-left, middle-center, middle-right
    6: "Left", 7: "Center", 8: "Right",     # lower-left, lower-center, lower-right
}
_TEXT_ANCHOR_Y: dict[int, str] = {
    0: "Top", 1: "Top", 2: "Top",
    3: "Center", 4: "Center", 5: "Center",
    6: "Bottom", 7: "Bottom", 8: "Bottom",
}


def _detect_ui_class(components: list[Any]) -> str:
    """
    Determine the Roblox UI class from a node's components.

    Returns the Roblox class name (TextLabel, ImageLabel, etc.) or "Frame".
    """
    for comp in components:
        ct = getattr(comp, "component_type", "")
        if ct in _UI_TYPE_MAP:
            return _UI_TYPE_MAP[ct]
    return "Frame"


def _extract_text_properties(components: list[Any]) -> dict[str, Any]:
    """Extract text content and style from Unity Text component."""
    for comp in components:
        ct = getattr(comp, "component_type", "")
        if ct in ("Text", "UnityEngine.UI.Text"):
            props = getattr(comp, "properties", {})
            result: dict[str, Any] = {}
            result["text"] = props.get("m_Text", "")
            # Font size
            result["text_size"] = int(_safe_float(props.get("m_FontSize", 14)))
            # Color
            color = props.get("m_Color", {})
            if isinstance(color, dict):
                result["text_color"] = (
                    _safe_float(color.get("r", 0)),
                    _safe_float(color.get("g", 0)),
                    _safe_float(color.get("b", 0)),
                )
            # Alignment
            anchor = int(_safe_float(props.get("m_Alignment", 4)))
            result["text_x_alignment"] = _TEXT_ANCHOR_X.get(anchor, "Center")
            result["text_y_alignment"] = _TEXT_ANCHOR_Y.get(anchor, "Center")
            # Font
            font_name = str(props.get("m_Font", {}).get("m_Name", "")) if isinstance(props.get("m_Font"), dict) else ""
            result["font"] = _FONT_MAP.get(font_name, "SourceSans")
            return result
    return {}


def _extract_image_properties(components: list[Any]) -> dict[str, Any]:
    """Extract image source and color from Unity Image/RawImage component."""
    for comp in components:
        ct = getattr(comp, "component_type", "")
        if ct in ("Image", "UnityEngine.UI.Image", "RawImage", "UnityEngine.UI.RawImage"):
            props = getattr(comp, "properties", {})
            result: dict[str, Any] = {}
            # Sprite reference (GUID — would need resolution)
            sprite = props.get("m_Sprite", {})
            if isinstance(sprite, dict) and sprite.get("guid"):
                result["image"] = f"rbxassetid://{sprite['guid']}"
            # Color tint
            color = props.get("m_Color", {})
            if isinstance(color, dict):
                result["image_color"] = (
                    _safe_float(color.get("r", 1)),
                    _safe_float(color.get("g", 1)),
                    _safe_float(color.get("b", 1)),
                )
                result["image_transparency"] = 1.0 - _safe_float(color.get("a", 1))
            return result
    return {}


def _is_image_component(comp: Any) -> bool:
    """Detect Unity Image component (may be classified as MonoBehaviour)."""
    ct = getattr(comp, "component_type", "")
    if ct in ("Image", "UnityEngine.UI.Image"):
        return True
    # Scene parser classifies all script-based components as MonoBehaviour.
    # Detect Image by its well-known script GUID or presence of m_Sprite.
    if ct == "MonoBehaviour":
        props = getattr(comp, "properties", {})
        script = props.get("m_Script", {})
        if isinstance(script, dict):
            guid = script.get("guid", "")
            # fe87c0e1cc204ed48ad3b37840f39efc = UnityEngine.UI.Image
            if guid.startswith("fe87c0e1cc204ed48ad3"):
                return True
        # Fallback: has m_Sprite field (unique to Image)
        if "m_Sprite" in props:
            return True
    return False


def _extract_background_color(components: list[Any]) -> dict[str, Any]:
    """Extract background color from Unity Image component used as background."""
    for comp in components:
        if _is_image_component(comp):
            props = getattr(comp, "properties", {})
            color = props.get("m_Color", {})
            if isinstance(color, dict):
                return {
                    "background_color": (
                        _safe_float(color.get("r", 1)),
                        _safe_float(color.get("g", 1)),
                        _safe_float(color.get("b", 1)),
                    ),
                    "background_transparency": 1.0 - _safe_float(color.get("a", 1)),
                }
    return {}


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
        components = getattr(node, "components", [])
        for comp in components:
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

        # Detect UI class from component types
        elem.class_name = _detect_ui_class(components)

        # Extract component-specific properties
        if elem.class_name in ("TextLabel", "TextButton", "TextBox"):
            text_props = _extract_text_properties(components)
            if text_props:
                elem.text = text_props.get("text", "")
                elem.text_color = text_props.get("text_color", (0.0, 0.0, 0.0))
                elem.text_size = text_props.get("text_size", 14)
                elem.font = text_props.get("font", "SourceSans")
                elem.text_x_alignment = text_props.get("text_x_alignment", "Center")
                elem.text_y_alignment = text_props.get("text_y_alignment", "Center")

        if elem.class_name in ("ImageLabel", "ImageButton"):
            img_props = _extract_image_properties(components)
            if img_props:
                elem.image = img_props.get("image", "")
                elem.image_color = img_props.get("image_color", (1.0, 1.0, 1.0))
                elem.image_transparency = img_props.get("image_transparency", 0.0)

        if elem.class_name == "Frame":
            bg_props = _extract_background_color(components)
            if bg_props:
                elem.background_color = bg_props.get("background_color", (1.0, 1.0, 1.0))
                elem.background_transparency = bg_props.get("background_transparency", 0.0)
            else:
                # No Image component → no visual background in Unity → transparent
                elem.background_transparency = 1.0

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


def to_rbx_ui_element(elem: RobloxUIElement) -> Any:
    """
    Convert a RobloxUIElement to an RbxUIElement for rbxl_writer.

    This bridges the ui_translator output to the rbxl_writer input format.
    Import is deferred to avoid circular dependencies.
    """
    from modules.rbxl_writer import RbxUIElement

    rbx = RbxUIElement(
        name=elem.name,
        class_name=elem.class_name,
        position_x_scale=elem.position_x_scale,
        position_x_offset=elem.position_x_offset,
        position_y_scale=elem.position_y_scale,
        position_y_offset=elem.position_y_offset,
        size_x_scale=elem.size_x_scale,
        size_x_offset=elem.size_x_offset,
        size_y_scale=elem.size_y_scale,
        size_y_offset=elem.size_y_offset,
        anchor_point_x=elem.anchor_point_x,
        anchor_point_y=elem.anchor_point_y,
        background_color=elem.background_color,
        background_transparency=elem.background_transparency,
        text=elem.text,
        text_color=elem.text_color,
        text_size=elem.text_size,
        font=elem.font,
        text_x_alignment=elem.text_x_alignment,
        text_y_alignment=elem.text_y_alignment,
        image=elem.image,
        image_color=elem.image_color,
        image_transparency=elem.image_transparency,
        children=[to_rbx_ui_element(c) for c in elem.children],
    )
    return rbx


def to_rbx_screen_gui(
    name: str,
    elements: list[RobloxUIElement],
) -> Any:
    """
    Create an RbxScreenGui from a list of translated UI elements.

    Import is deferred to avoid circular dependencies.
    """
    from modules.rbxl_writer import RbxScreenGui

    return RbxScreenGui(
        name=name,
        elements=[to_rbx_ui_element(e) for e in elements],
    )
