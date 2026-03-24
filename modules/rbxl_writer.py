"""
rbxl_writer.py — Writes a Roblox place file (.rbxl) from converted scene data.

A .rbxl file is an XML document conforming to Roblox's place format. This
module takes the parsed scene hierarchy, transpiled scripts, and prefab
templates, then serialises them into a valid .rbxl XML file that can be
opened directly in Roblox Studio.

Reference format: https://dom.rojo.space/binary (text/XML variant used here)
No other module is imported here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from xml.dom import minidom


# ---------------------------------------------------------------------------
# Data types consumed by this module (mirror of upstream shapes)
# ---------------------------------------------------------------------------

@dataclass
class RbxScriptEntry:
    name: str
    luau_source: str
    script_type: str = "Script"   # "Script" | "LocalScript" | "ModuleScript"


@dataclass
class RbxSurfaceAppearance:
    """PBR material properties for a SurfaceAppearance child object."""
    color_map: str | None = None         # texture asset path / placeholder
    normal_map: str | None = None
    metalness_map: str | None = None
    roughness_map: str | None = None
    emissive_mask: str | None = None
    emissive_strength: float = 1.0
    emissive_tint: tuple[float, float, float] = (1.0, 1.0, 1.0)
    color_tint: tuple[float, float, float] = (1.0, 1.0, 1.0)
    alpha_mode: str = "Opaque"           # Opaque | Transparency | Overlay


@dataclass
class RbxPartEntry:
    name: str
    position: tuple[float, float, float] = (0.0, 4.0, 0.0)
    rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)  # quaternion (x,y,z,w)
    size: tuple[float, float, float] = (4.0, 1.0, 2.0)
    brick_color: str = "Medium stone grey"
    anchored: bool = True
    children: list["RbxPartEntry"] = field(default_factory=list)
    scripts: list[RbxScriptEntry] = field(default_factory=list)
    color3: tuple[float, float, float] | None = None
    transparency: float = 0.0
    material_enum: str | None = None     # e.g. "SmoothPlastic"
    surface_appearance: RbxSurfaceAppearance | None = None
    can_collide: bool = True
    mesh_id: str | None = None           # rbxassetid:// or file path for MeshPart
    shape: str | None = None             # "Block" | "Ball" | "Cylinder" | "Wedge" (Part only)
    # Child objects converted from Unity Light, AudioSource, ParticleSystem components
    light_children: list[tuple] = field(default_factory=list)
    sound_children: list[tuple] = field(default_factory=list)
    particle_children: list[tuple] = field(default_factory=list)


@dataclass
class RbxLightingConfig:
    """Global lighting properties derived from Unity's Directional Light."""
    brightness: float = 1.0
    ambient: tuple[float, float, float] = (0.5, 0.5, 0.5)
    color_shift_top: tuple[float, float, float] = (1.0, 1.0, 1.0)
    outdoor_ambient: tuple[float, float, float] = (0.5, 0.5, 0.5)
    clock_time: float = 14.0  # 2pm (sun high and forward)
    geographic_latitude: float = 0.0


@dataclass
class RbxCameraConfig:
    """Camera settings derived from Unity's main Camera component."""
    position: tuple[float, float, float] = (0.0, 10.0, -20.0)
    rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)  # quaternion
    field_of_view: float = 70.0
    near_clip: float = 0.3
    far_clip: float = 1000.0


@dataclass
class RbxSkyboxConfig:
    """Skybox settings derived from Unity's RenderSettings + Skybox material."""
    front: str | None = None   # texture paths for 6-sided skybox
    back: str | None = None
    left: str | None = None
    right: str | None = None
    up: str | None = None
    down: str | None = None
    celestial_bodies_shown: bool = True
    star_count: int = 3000


@dataclass
class RbxUIElement:
    """A Roblox UI element for ScreenGui output."""
    name: str
    class_name: str = "Frame"  # Frame, TextLabel, TextButton, ImageLabel, ImageButton, ScrollingFrame
    # Position as UDim2(xScale, xOffset, yScale, yOffset)
    position_x_scale: float = 0.0
    position_x_offset: int = 0
    position_y_scale: float = 0.0
    position_y_offset: int = 0
    # Size as UDim2
    size_x_scale: float = 0.0
    size_x_offset: int = 100
    size_y_scale: float = 0.0
    size_y_offset: int = 100
    # AnchorPoint
    anchor_point_x: float = 0.0
    anchor_point_y: float = 0.0
    # Appearance
    background_color: tuple[float, float, float] = (1.0, 1.0, 1.0)
    background_transparency: float = 0.0
    border_size: int = 0
    # Text (for TextLabel/TextButton)
    text: str = ""
    text_color: tuple[float, float, float] = (0.0, 0.0, 0.0)
    text_size: int = 14
    font: str = "SourceSans"
    text_x_alignment: str = "Center"  # Left | Center | Right
    text_y_alignment: str = "Center"  # Top | Center | Bottom
    # Image (for ImageLabel/ImageButton)
    image: str = ""  # texture asset path
    image_color: tuple[float, float, float] = (1.0, 1.0, 1.0)
    image_transparency: float = 0.0
    # Visibility
    visible: bool = True
    z_index: int = 1
    # Children
    children: list["RbxUIElement"] = field(default_factory=list)


@dataclass
class RbxScreenGui:
    """A ScreenGui container to be placed in StarterGui."""
    name: str = "ConvertedUI"
    elements: list[RbxUIElement] = field(default_factory=list)
    display_order: int = 0
    reset_on_spawn: bool = False


@dataclass
class RbxWriteResult:
    """Outcome of writing a .rbxl file."""
    output_path: Path
    parts_written: int
    scripts_written: int
    ui_elements_written: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass
class RbxPackageEntry:
    """Outcome of writing a single .rbxm package file."""
    prefab_name: str
    output_path: Path
    parts_written: int
    scripts_written: int


@dataclass
class RbxPackageResult:
    """Outcome of writing all .rbxm package files."""
    packages: list[RbxPackageEntry] = field(default_factory=list)
    total_packages: int = 0
    warnings: list[str] = field(default_factory=list)
    # Converted part trees for embedding in ServerStorage inside the .rbxl.
    # Each tuple is (model_name, root_part).
    server_storage_templates: list[tuple[str, RbxPartEntry]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# XML helpers
# ---------------------------------------------------------------------------

def _make_property(parent: ET.Element, prop_type: str, name: str, value: Any) -> ET.Element:
    el = ET.SubElement(parent, prop_type, name=name)
    el.text = str(value)
    return el


def _make_vector3(parent: ET.Element, name: str, xyz: tuple[float, float, float]) -> ET.Element:
    el = ET.SubElement(parent, "Vector3", name=name)
    ET.SubElement(el, "X").text = str(xyz[0])
    ET.SubElement(el, "Y").text = str(xyz[1])
    ET.SubElement(el, "Z").text = str(xyz[2])
    return el


def _make_color3(parent: ET.Element, name: str, rgb: tuple[float, float, float]) -> ET.Element:
    el = ET.SubElement(parent, "Color3", name=name)
    # Roblox Color3 uses 0-1 float values
    ET.SubElement(el, "R").text = f"{rgb[0]:.6f}"
    ET.SubElement(el, "G").text = f"{rgb[1]:.6f}"
    ET.SubElement(el, "B").text = f"{rgb[2]:.6f}"
    return el


def _make_udim2(parent: ET.Element, name: str,
                xs: float, xo: int, ys: float, yo: int) -> ET.Element:
    """Create a UDim2 property: UDim2.new(xScale, xOffset, yScale, yOffset)."""
    el = ET.SubElement(parent, "UDim2", name=name)
    x_el = ET.SubElement(el, "XS")
    x_el.text = f"{xs:.6f}"
    ET.SubElement(el, "XO").text = str(xo)
    y_el = ET.SubElement(el, "YS")
    y_el.text = f"{ys:.6f}"
    ET.SubElement(el, "YO").text = str(yo)
    return el


def _make_vector2(parent: ET.Element, name: str, xy: tuple[float, float]) -> ET.Element:
    el = ET.SubElement(parent, "Vector2", name=name)
    ET.SubElement(el, "X").text = f"{xy[0]:.6f}"
    ET.SubElement(el, "Y").text = f"{xy[1]:.6f}"
    return el


def _make_ui_element(parent: ET.Element, elem: "RbxUIElement") -> None:
    """Serialise a RbxUIElement to XML under the given parent."""
    item = ET.SubElement(parent, "Item", **{"class": elem.class_name})
    props = ET.SubElement(item, "Properties")
    _make_property(props, "string", "Name", elem.name)

    # Position and Size as UDim2
    _make_udim2(props, "Position",
                elem.position_x_scale, elem.position_x_offset,
                elem.position_y_scale, elem.position_y_offset)
    _make_udim2(props, "Size",
                elem.size_x_scale, elem.size_x_offset,
                elem.size_y_scale, elem.size_y_offset)

    # AnchorPoint
    _make_vector2(props, "AnchorPoint",
                  (elem.anchor_point_x, elem.anchor_point_y))

    # Appearance
    _make_color3(props, "BackgroundColor3", elem.background_color)
    _make_property(props, "float", "BackgroundTransparency",
                   f"{elem.background_transparency:.4f}")
    _make_property(props, "int", "BorderSizePixel", str(elem.border_size))
    _make_property(props, "bool", "Visible", str(elem.visible).lower())
    _make_property(props, "int", "ZIndex", str(elem.z_index))

    # Text properties (TextLabel / TextButton)
    if elem.class_name in ("TextLabel", "TextButton"):
        _make_property(props, "string", "Text", elem.text)
        _make_color3(props, "TextColor3", elem.text_color)
        _make_property(props, "int", "TextSize", str(elem.text_size))
        _make_property(props, "token", "Font", elem.font)
        _make_property(props, "token", "TextXAlignment", elem.text_x_alignment)
        _make_property(props, "token", "TextYAlignment", elem.text_y_alignment)

    # Image properties (ImageLabel / ImageButton)
    if elem.class_name in ("ImageLabel", "ImageButton"):
        _make_property(props, "Content", "Image", elem.image)
        _make_color3(props, "ImageColor3", elem.image_color)
        _make_property(props, "float", "ImageTransparency",
                       f"{elem.image_transparency:.4f}")

    # Recurse into children
    for child in elem.children:
        _make_ui_element(item, child)


def _count_ui_elements(elements: list["RbxUIElement"]) -> int:
    """Count total UI elements including nested children."""
    count = 0
    for elem in elements:
        count += 1
        count += _count_ui_elements(elem.children)
    return count


def _quat_to_rotation_matrix(
    qx: float, qy: float, qz: float, qw: float,
) -> tuple[float, float, float, float, float, float, float, float, float]:
    """
    Convert a quaternion (x, y, z, w) to a 3×3 rotation matrix.

    Returns (R00, R01, R02, R10, R11, R12, R20, R21, R22) in row-major order,
    matching Roblox's CFrame CoordinateFrame property layout.
    """
    # Normalise
    mag = math.sqrt(qx*qx + qy*qy + qz*qz + qw*qw)
    if mag < 1e-10:
        return (1, 0, 0, 0, 1, 0, 0, 0, 1)
    qx, qy, qz, qw = qx/mag, qy/mag, qz/mag, qw/mag

    r00 = 1 - 2*(qy*qy + qz*qz)
    r01 = 2*(qx*qy - qz*qw)
    r02 = 2*(qx*qz + qy*qw)
    r10 = 2*(qx*qy + qz*qw)
    r11 = 1 - 2*(qx*qx + qz*qz)
    r12 = 2*(qy*qz - qx*qw)
    r20 = 2*(qx*qz - qy*qw)
    r21 = 2*(qy*qz + qx*qw)
    r22 = 1 - 2*(qx*qx + qy*qy)

    return (r00, r01, r02, r10, r11, r12, r20, r21, r22)


def _is_identity_quat(q: tuple[float, float, float, float]) -> bool:
    """Check if a quaternion is approximately identity (no rotation)."""
    return abs(q[0]) < 1e-6 and abs(q[1]) < 1e-6 and abs(q[2]) < 1e-6 and abs(q[3] - 1.0) < 1e-6


def _make_cframe(
    parent: ET.Element,
    name: str,
    pos: tuple[float, float, float],
    quat: tuple[float, float, float, float],
) -> ET.Element:
    """Write a CFrame property as a CoordinateFrame element (position + 3×3 rotation matrix)."""
    el = ET.SubElement(parent, "CoordinateFrame", name=name)
    ET.SubElement(el, "X").text = str(pos[0])
    ET.SubElement(el, "Y").text = str(pos[1])
    ET.SubElement(el, "Z").text = str(pos[2])
    r = _quat_to_rotation_matrix(*quat)
    ET.SubElement(el, "R00").text = f"{r[0]:.8f}"
    ET.SubElement(el, "R01").text = f"{r[1]:.8f}"
    ET.SubElement(el, "R02").text = f"{r[2]:.8f}"
    ET.SubElement(el, "R10").text = f"{r[3]:.8f}"
    ET.SubElement(el, "R11").text = f"{r[4]:.8f}"
    ET.SubElement(el, "R12").text = f"{r[5]:.8f}"
    ET.SubElement(el, "R20").text = f"{r[6]:.8f}"
    ET.SubElement(el, "R21").text = f"{r[7]:.8f}"
    ET.SubElement(el, "R22").text = f"{r[8]:.8f}"
    return el


def _make_light(
    parent: ET.Element,
    light_class: str,
    color: tuple[float, float, float],
    brightness: float,
    range_val: float,
    shadows: bool,
    angle: float = 90.0,
) -> ET.Element:
    """Emit a PointLight, SpotLight, or SurfaceLight child item under a Part."""
    item = ET.SubElement(parent, "Item", **{"class": light_class})
    props = ET.SubElement(item, "Properties")
    _make_property(props, "string", "Name", light_class)
    _make_color3(props, "Color", color)
    _make_property(props, "float", "Brightness", f"{brightness:.4f}")
    _make_property(props, "float", "Range", f"{range_val:.2f}")
    _make_property(props, "bool", "Shadows", str(shadows).lower())
    _make_property(props, "bool", "Enabled", "true")
    if light_class == "SpotLight":
        _make_property(props, "float", "Angle", f"{angle:.2f}")
        _make_property(props, "token", "Face", "5")  # Front face
    return item


def _make_sound(
    parent: ET.Element,
    name: str,
    sound_path: str,
    volume: float,
    looped: bool,
    playback_speed: float,
    playing: bool,
    roll_off_min: float,
    roll_off_max: float,
) -> ET.Element:
    """Emit a Sound child item under a Part."""
    item = ET.SubElement(parent, "Item", **{"class": "Sound"})
    props = ET.SubElement(item, "Properties")
    _make_property(props, "string", "Name", name)
    # SoundId will need to be an uploaded asset URL; for now store the path as a comment
    _make_property(props, "Content", "SoundId", f"-- TODO: upload {sound_path}")
    _make_property(props, "float", "Volume", f"{volume:.4f}")
    _make_property(props, "bool", "Looped", str(looped).lower())
    _make_property(props, "float", "PlaybackSpeed", f"{playback_speed:.4f}")
    _make_property(props, "bool", "Playing", str(playing).lower())
    _make_property(props, "float", "RollOffMinDistance", f"{roll_off_min:.2f}")
    _make_property(props, "float", "RollOffMaxDistance", f"{roll_off_max:.2f}")
    return item


def _make_particle_emitter(
    parent: ET.Element,
    name: str,
    rate: float,
    lifetime_min: float,
    lifetime_max: float,
    speed_min: float,
    speed_max: float,
    size: float,
    color: tuple[float, float, float],
    texture_path: str | None,
    light_emission: float,
    transparency: float,
) -> ET.Element:
    """Emit a ParticleEmitter child item under a Part."""
    item = ET.SubElement(parent, "Item", **{"class": "ParticleEmitter"})
    props = ET.SubElement(item, "Properties")
    _make_property(props, "string", "Name", name)
    _make_property(props, "float", "Rate", f"{rate:.2f}")
    _make_property(props, "bool", "Enabled", "true")
    # Lifetime as NumberRange
    lr = ET.SubElement(props, "NumberRange", name="Lifetime")
    lr.text = f"{lifetime_min:.4f} {lifetime_max:.4f}"
    # Speed as NumberRange
    sr = ET.SubElement(props, "NumberRange", name="Speed")
    sr.text = f"{speed_min:.4f} {speed_max:.4f}"
    # Size as NumberSequence (constant)
    ss = ET.SubElement(props, "NumberSequence", name="Size")
    k1 = ET.SubElement(ss, "Keypoint")
    k1.set("time", "0")
    k1.set("value", f"{size:.4f}")
    k1.set("envelope", "0")
    k2 = ET.SubElement(ss, "Keypoint")
    k2.set("time", "1")
    k2.set("value", f"{size:.4f}")
    k2.set("envelope", "0")
    _make_color3(props, "Color", color)
    if texture_path:
        _make_property(props, "Content", "Texture", f"-- TODO: upload {texture_path}")
    _make_property(props, "float", "LightEmission", f"{light_emission:.4f}")
    # Transparency as NumberSequence (constant)
    ts = ET.SubElement(props, "NumberSequence", name="Transparency")
    tk1 = ET.SubElement(ts, "Keypoint")
    tk1.set("time", "0")
    tk1.set("value", f"{transparency:.4f}")
    tk1.set("envelope", "0")
    tk2 = ET.SubElement(ts, "Keypoint")
    tk2.set("time", "1")
    tk2.set("value", "1")  # fade out at end of lifetime
    tk2.set("envelope", "0")
    return item


def _make_surface_appearance(parent: ET.Element, sa: RbxSurfaceAppearance) -> ET.Element:
    """Emit a SurfaceAppearance child item under a Part/MeshPart."""
    item = ET.SubElement(parent, "Item", **{"class": "SurfaceAppearance"})
    props = ET.SubElement(item, "Properties")
    _make_property(props, "string", "Name", "SurfaceAppearance")
    if sa.color_map:
        _make_property(props, "Content", "ColorMap", sa.color_map)
    if sa.normal_map:
        _make_property(props, "Content", "NormalMap", sa.normal_map)
    if sa.metalness_map:
        _make_property(props, "Content", "MetalnessMap", sa.metalness_map)
    if sa.roughness_map:
        _make_property(props, "Content", "RoughnessMap", sa.roughness_map)
    if sa.emissive_mask:
        _make_property(props, "Content", "EmissiveMaskContent", sa.emissive_mask)
        _make_property(props, "float", "EmissiveStrength", f"{sa.emissive_strength:.4f}")
        _make_color3(props, "EmissiveTint", sa.emissive_tint)
    if sa.color_tint != (1.0, 1.0, 1.0):
        _make_color3(props, "Color", sa.color_tint)
    _make_property(props, "token", "AlphaMode", _ALPHA_MODE_MAP.get(sa.alpha_mode, "0"))
    return item


_ALPHA_MODE_MAP = {"Overlay": "0", "Transparency": "1", "Opaque": "2", "TintMask": "3"}


def _is_grouping_node(part: RbxPartEntry) -> bool:
    """Determine if a part should be a Model (grouping container) instead of a Part.

    A node is a grouping container when it has children but no geometry of its
    own (no mesh, no primitive shape, no lights/sounds/particles).
    """
    if part.mesh_id is not None or part.shape is not None:
        return False
    if part.light_children or part.sound_children or part.particle_children:
        return False
    if not part.children:
        return False
    return True


def _make_part(workspace: ET.Element, part: RbxPartEntry) -> ET.Element:
    # Use Model for pure grouping containers (children but no geometry).
    # Use MeshPart when a mesh asset is available (required for SurfaceAppearance),
    # otherwise fall back to a plain Part (box primitive).
    if _is_grouping_node(part):
        item = ET.SubElement(workspace, "Item", **{"class": "Model"})
        props = ET.SubElement(item, "Properties")
        _make_property(props, "string", "Name", part.name)

        for script in part.scripts:
            script_item = ET.SubElement(item, "Item", **{"class": script.script_type})
            sprops = ET.SubElement(script_item, "Properties")
            _make_property(sprops, "string", "Name", script.name)
            _make_property(sprops, "ProtectedString", "Source", script.luau_source)

        for child in part.children:
            _make_part(item, child)

        return item

    use_mesh = part.mesh_id is not None
    cls = "MeshPart" if use_mesh else "Part"
    item = ET.SubElement(workspace, "Item", **{"class": cls})
    props = ET.SubElement(item, "Properties")
    _make_property(props, "string", "Name", part.name)
    _make_property(props, "bool", "Anchored", str(part.anchored).lower())

    # Write CFrame (position + rotation). When rotation is identity, just set Position
    # for cleaner output. Otherwise, write a full CoordinateFrame with rotation matrix.
    if _is_identity_quat(part.rotation):
        _make_vector3(props, "Position", part.position)
    else:
        _make_cframe(props, "CFrame", part.position, part.rotation)

    _make_vector3(props, "Size", part.size)
    _make_property(props, "BrickColor", "BrickColor", part.brick_color)

    if use_mesh:
        _make_property(props, "Content", "MeshId", part.mesh_id)

    # Shape property for non-mesh primitives (Ball, Cylinder, Wedge)
    _SHAPE_TOKEN = {"Block": "1", "Ball": "3", "Cylinder": "2", "Wedge": "4"}
    if not use_mesh and part.shape and part.shape in _SHAPE_TOKEN:
        _make_property(props, "token", "shape", _SHAPE_TOKEN[part.shape])

    if part.color3:
        _make_color3(props, "Color3", part.color3)
    if part.transparency > 0.001:
        _make_property(props, "float", "Transparency", f"{part.transparency:.4f}")
    if not part.can_collide:
        _make_property(props, "bool", "CanCollide", "false")
    if part.material_enum:
        _make_property(props, "token", "Material", part.material_enum)

    # SurfaceAppearance child (only meaningful on MeshPart)
    if part.surface_appearance and use_mesh:
        _make_surface_appearance(item, part.surface_appearance)
    elif part.surface_appearance and not use_mesh:
        # No mesh — SurfaceAppearance won't render on a plain Part.
        # Apply what we can: color/transparency are already set via BasePart properties.
        pass

    # Light children (PointLight, SpotLight)
    for lc in part.light_children:
        _make_light(item, lc[0], lc[1], lc[2], lc[3], lc[4], lc[5])

    # Sound children
    for sc in part.sound_children:
        _make_sound(item, sc[0], sc[1], sc[2], sc[3], sc[4], sc[5], sc[6], sc[7])

    # ParticleEmitter children
    for pc in part.particle_children:
        _make_particle_emitter(item, pc[0], pc[1], pc[2], pc[3], pc[4], pc[5], pc[6], pc[7], pc[8], pc[9], pc[10])

    for script in part.scripts:
        script_item = ET.SubElement(item, "Item", **{"class": script.script_type})
        sprops = ET.SubElement(script_item, "Properties")
        _make_property(sprops, "string", "Name", script.name)
        _make_property(sprops, "ProtectedString", "Source", script.luau_source)

    for child in part.children:
        _make_part(item, child)

    return item


def _prettify(tree: ET.Element) -> str:
    raw = ET.tostring(tree, encoding="unicode")
    reparsed = minidom.parseString(raw)
    return reparsed.toprettyxml(indent="  ")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _count_parts(parts: list[RbxPartEntry]) -> int:
    """Count all parts including nested children."""
    count = 0
    for part in parts:
        count += 1
        if part.children:
            count += _count_parts(part.children)
    return count


def write_rbxl(
    parts: list[RbxPartEntry],
    scripts: list[RbxScriptEntry],
    output_path: str | Path,
    place_name: str = "ConvertedPlace",
    lighting: RbxLightingConfig | None = None,
    camera: RbxCameraConfig | None = None,
    skybox: RbxSkyboxConfig | None = None,
    server_storage_templates: list[tuple[str, RbxPartEntry]] | None = None,
    screen_guis: list[RbxScreenGui] | None = None,
) -> RbxWriteResult:
    """
    Serialise the converted scene into a Roblox place file (.rbxl).

    Args:
        parts: List of RbxPartEntry objects (geometry + scripts).
        scripts: Top-level scripts placed directly in ServerScriptService.
        output_path: Destination .rbxl file path (created/overwritten).
        place_name: Name embedded in the DataModel root.
        lighting: Optional lighting configuration from directional lights.
        camera: Optional camera configuration from Unity Camera component.
        skybox: Optional skybox configuration from Unity RenderSettings.
        server_storage_templates: Optional prefab templates to place in
            ServerStorage for runtime Clone(). Each tuple is
            (model_name, root_part_entry).
        screen_guis: Optional list of ScreenGui objects to place in StarterGui.
            Generated from Unity Canvas / RectTransform UI hierarchy.

    Returns:
        RbxWriteResult describing what was written.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []

    # Root DataModel
    root = ET.Element("roblox", **{
        "xmlns:xmime": "http://www.w3.org/2005/05/xmlmime",
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xsi:noNamespaceSchemaLocation":
            "https://raw.githubusercontent.com/MaximumADHD/Roblox-File-Format/main/Schema/roblox.xsd",
        "version": "4",
    })

    # Lighting service (from directional lights or defaults)
    if lighting:
        light_item = ET.SubElement(root, "Item", **{"class": "Lighting"})
        lp = ET.SubElement(light_item, "Properties")
        _make_property(lp, "string", "Name", "Lighting")
        _make_property(lp, "float", "Brightness", f"{lighting.brightness:.4f}")
        _make_color3(lp, "Ambient", lighting.ambient)
        _make_color3(lp, "ColorShift_Top", lighting.color_shift_top)
        _make_color3(lp, "OutdoorAmbient", lighting.outdoor_ambient)
        _make_property(lp, "float", "ClockTime", f"{lighting.clock_time:.2f}")
        _make_property(lp, "float", "GeographicLatitude", f"{lighting.geographic_latitude:.2f}")

        # Skybox child of Lighting
        if skybox:
            sky_item = ET.SubElement(light_item, "Item", **{"class": "Sky"})
            sp = ET.SubElement(sky_item, "Properties")
            _make_property(sp, "string", "Name", "Sky")
            _make_property(sp, "bool", "CelestialBodiesShown",
                           str(skybox.celestial_bodies_shown).lower())
            _make_property(sp, "int", "StarCount", str(skybox.star_count))
            for face, attr in [("SkyboxFt", "front"), ("SkyboxBk", "back"),
                                ("SkyboxLf", "left"), ("SkyboxRt", "right"),
                                ("SkyboxUp", "up"), ("SkyboxDn", "down")]:
                tex_path = getattr(skybox, attr)
                if tex_path:
                    _make_property(sp, "Content", face, tex_path)
    elif skybox:
        # Skybox without explicit lighting — create Lighting container for it
        light_item = ET.SubElement(root, "Item", **{"class": "Lighting"})
        lp = ET.SubElement(light_item, "Properties")
        _make_property(lp, "string", "Name", "Lighting")
        sky_item = ET.SubElement(light_item, "Item", **{"class": "Sky"})
        sp = ET.SubElement(sky_item, "Properties")
        _make_property(sp, "string", "Name", "Sky")
        for face, attr in [("SkyboxFt", "front"), ("SkyboxBk", "back"),
                            ("SkyboxLf", "left"), ("SkyboxRt", "right"),
                            ("SkyboxUp", "up"), ("SkyboxDn", "down")]:
            tex_path = getattr(skybox, attr)
            if tex_path:
                _make_property(sp, "Content", face, tex_path)

    # Workspace
    workspace_item = ET.SubElement(root, "Item", **{"class": "Workspace"})
    ws_props = ET.SubElement(workspace_item, "Properties")
    _make_property(ws_props, "string", "Name", "Workspace")

    # Camera configuration (set on Workspace.CurrentCamera)
    if camera:
        cam_item = ET.SubElement(workspace_item, "Item", **{"class": "Camera"})
        cp = ET.SubElement(cam_item, "Properties")
        _make_property(cp, "string", "Name", "Camera")
        _make_cframe(cp, "CFrame", camera.position, camera.rotation)
        _make_property(cp, "float", "FieldOfView", f"{camera.field_of_view:.1f}")
        _make_property(cp, "float", "NearPlaneZ", f"{camera.near_clip:.2f}")
        _make_property(cp, "float", "FarPlaneZ", f"{camera.far_clip:.1f}")

    for part in parts:
        _make_part(workspace_item, part)

    # Count all parts including children for accurate reporting
    parts_written = _count_parts(parts)

    # ServerStorage — prefab templates for runtime Clone()
    if server_storage_templates:
        ss_item = ET.SubElement(root, "Item", **{"class": "ServerStorage"})
        ss_props = ET.SubElement(ss_item, "Properties")
        _make_property(ss_props, "string", "Name", "ServerStorage")

        for model_name, root_part in server_storage_templates:
            model_item = ET.SubElement(ss_item, "Item", **{"class": "Model"})
            mp = ET.SubElement(model_item, "Properties")
            _make_property(mp, "string", "Name", model_name)
            _make_part(model_item, root_part)

    # Partition scripts by type into appropriate Roblox containers:
    #   Script       → ServerScriptService
    #   LocalScript  → StarterPlayer.StarterPlayerScripts
    #   ModuleScript → ReplicatedStorage
    server_scripts = [s for s in scripts if s.script_type == "Script"]
    local_scripts = [s for s in scripts if s.script_type == "LocalScript"]
    module_scripts = [s for s in scripts if s.script_type == "ModuleScript"]

    # ServerScriptService — server Scripts
    sss_item = ET.SubElement(root, "Item", **{"class": "ServerScriptService"})
    sss_props = ET.SubElement(sss_item, "Properties")
    _make_property(sss_props, "string", "Name", "ServerScriptService")

    scripts_written = 0
    for script in server_scripts:
        si = ET.SubElement(sss_item, "Item", **{"class": "Script"})
        sp = ET.SubElement(si, "Properties")
        _make_property(sp, "string", "Name", script.name)
        _make_property(sp, "ProtectedString", "Source", script.luau_source)
        scripts_written += 1

    # StarterPlayer.StarterPlayerScripts — LocalScripts
    if local_scripts:
        sp_item = ET.SubElement(root, "Item", **{"class": "StarterPlayer"})
        sp_props = ET.SubElement(sp_item, "Properties")
        _make_property(sp_props, "string", "Name", "StarterPlayer")

        sps_item = ET.SubElement(sp_item, "Item", **{"class": "StarterPlayerScripts"})
        sps_props = ET.SubElement(sps_item, "Properties")
        _make_property(sps_props, "string", "Name", "StarterPlayerScripts")

        for script in local_scripts:
            si = ET.SubElement(sps_item, "Item", **{"class": "LocalScript"})
            sp = ET.SubElement(si, "Properties")
            _make_property(sp, "string", "Name", script.name)
            _make_property(sp, "ProtectedString", "Source", script.luau_source)
            scripts_written += 1

    # ReplicatedStorage — ModuleScripts (accessible to both client and server)
    if module_scripts:
        rs_item = ET.SubElement(root, "Item", **{"class": "ReplicatedStorage"})
        rs_props = ET.SubElement(rs_item, "Properties")
        _make_property(rs_props, "string", "Name", "ReplicatedStorage")

        for script in module_scripts:
            si = ET.SubElement(rs_item, "Item", **{"class": "ModuleScript"})
            sp = ET.SubElement(si, "Properties")
            _make_property(sp, "string", "Name", script.name)
            _make_property(sp, "ProtectedString", "Source", script.luau_source)
            scripts_written += 1

    # StarterGui — ScreenGui elements from Unity Canvas / RectTransform UI
    ui_elements_written = 0
    if screen_guis:
        sg_item = ET.SubElement(root, "Item", **{"class": "StarterGui"})
        sg_props = ET.SubElement(sg_item, "Properties")
        _make_property(sg_props, "string", "Name", "StarterGui")

        for gui in screen_guis:
            screen_gui_item = ET.SubElement(sg_item, "Item", **{"class": "ScreenGui"})
            sgui_props = ET.SubElement(screen_gui_item, "Properties")
            _make_property(sgui_props, "string", "Name", gui.name)
            _make_property(sgui_props, "int", "DisplayOrder", str(gui.display_order))
            _make_property(sgui_props, "bool", "ResetOnSpawn",
                           str(gui.reset_on_spawn).lower())

            for elem in gui.elements:
                _make_ui_element(screen_gui_item, elem)
            ui_elements_written += _count_ui_elements(gui.elements)

    xml_str = _prettify(root)
    output_path.write_text(xml_str, encoding="utf-8")

    return RbxWriteResult(
        output_path=output_path,
        parts_written=parts_written,
        scripts_written=scripts_written,
        ui_elements_written=ui_elements_written,
        warnings=warnings,
    )


def write_rbxm(
    parts: list[RbxPartEntry],
    scripts: list[RbxScriptEntry],
    output_path: str | Path,
    model_name: str = "Package",
) -> RbxPackageEntry:
    """
    Serialise a prefab into a Roblox model file (.rbxm).

    A .rbxm is structurally identical to .rbxl XML but the root contains a
    single Model item (instead of Workspace, ServerScriptService, etc.).
    This allows the model to be inserted into any place via the Toolbox
    or used as a Roblox Package.

    Args:
        parts: RbxPartEntry objects forming the model hierarchy.
        scripts: Scripts to attach inside the model (as children of the Model).
        output_path: Destination .rbxm file path.
        model_name: Name of the top-level Model instance.

    Returns:
        RbxPackageEntry describing what was written.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    root = ET.Element("roblox", **{
        "xmlns:xmime": "http://www.w3.org/2005/05/xmlmime",
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xsi:noNamespaceSchemaLocation":
            "https://raw.githubusercontent.com/MaximumADHD/Roblox-File-Format/main/Schema/roblox.xsd",
        "version": "4",
    })

    # Top-level Model container
    model_item = ET.SubElement(root, "Item", **{"class": "Model"})
    model_props = ET.SubElement(model_item, "Properties")
    _make_property(model_props, "string", "Name", model_name)

    for part in parts:
        _make_part(model_item, part)

    scripts_written = 0
    for script in scripts:
        si = ET.SubElement(model_item, "Item", **{"class": script.script_type})
        sp = ET.SubElement(si, "Properties")
        _make_property(sp, "string", "Name", script.name)
        _make_property(sp, "ProtectedString", "Source", script.luau_source)
        scripts_written += 1

    xml_str = _prettify(root)
    output_path.write_text(xml_str, encoding="utf-8")

    return RbxPackageEntry(
        prefab_name=model_name,
        output_path=output_path,
        parts_written=_count_parts(parts),
        scripts_written=scripts_written,
    )
