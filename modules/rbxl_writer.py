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
    size: tuple[float, float, float] = (4.0, 1.0, 2.0)
    brick_color: str = "Medium stone grey"
    anchored: bool = True
    children: list["RbxPartEntry"] = field(default_factory=list)
    scripts: list[RbxScriptEntry] = field(default_factory=list)
    color3: tuple[float, float, float] | None = None
    transparency: float = 0.0
    material_enum: str | None = None     # e.g. "SmoothPlastic"
    surface_appearance: RbxSurfaceAppearance | None = None
    mesh_id: str | None = None           # rbxassetid:// or file path for MeshPart


@dataclass
class RbxWriteResult:
    """Outcome of writing a .rbxl file."""
    output_path: Path
    parts_written: int
    scripts_written: int
    warnings: list[str] = field(default_factory=list)


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


def _make_part(workspace: ET.Element, part: RbxPartEntry) -> ET.Element:
    # Use MeshPart when a mesh asset is available (required for SurfaceAppearance),
    # otherwise fall back to a plain Part (box primitive).
    use_mesh = part.mesh_id is not None
    cls = "MeshPart" if use_mesh else "Part"
    item = ET.SubElement(workspace, "Item", **{"class": cls})
    props = ET.SubElement(item, "Properties")
    _make_property(props, "string", "Name", part.name)
    _make_property(props, "bool", "Anchored", str(part.anchored).lower())
    _make_vector3(props, "Position", part.position)
    _make_vector3(props, "Size", part.size)
    _make_property(props, "BrickColor", "BrickColor", part.brick_color)

    if use_mesh:
        _make_property(props, "Content", "MeshId", part.mesh_id)

    if part.color3:
        _make_color3(props, "Color3", part.color3)
    if part.transparency > 0.001:
        _make_property(props, "float", "Transparency", f"{part.transparency:.4f}")
    if part.material_enum:
        _make_property(props, "token", "Material", part.material_enum)

    # SurfaceAppearance child (only meaningful on MeshPart)
    if part.surface_appearance and use_mesh:
        _make_surface_appearance(item, part.surface_appearance)
    elif part.surface_appearance and not use_mesh:
        # No mesh — SurfaceAppearance won't render on a plain Part.
        # Apply what we can: color/transparency are already set via BasePart properties.
        pass

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

def write_rbxl(
    parts: list[RbxPartEntry],
    scripts: list[RbxScriptEntry],
    output_path: str | Path,
    place_name: str = "ConvertedPlace",
) -> RbxWriteResult:
    """
    Serialise the converted scene into a Roblox place file (.rbxl).

    Args:
        parts: List of RbxPartEntry objects (geometry + scripts).
        scripts: Top-level scripts placed directly in ServerScriptService.
        output_path: Destination .rbxl file path (created/overwritten).
        place_name: Name embedded in the DataModel root.

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

    # Workspace
    workspace_item = ET.SubElement(root, "Item", **{"class": "Workspace"})
    ws_props = ET.SubElement(workspace_item, "Properties")
    _make_property(ws_props, "string", "Name", "Workspace")

    parts_written = 0
    for part in parts:
        _make_part(workspace_item, part)
        parts_written += 1

    # ServerScriptService for top-level scripts
    sss_item = ET.SubElement(root, "Item", **{"class": "ServerScriptService"})
    sss_props = ET.SubElement(sss_item, "Properties")
    _make_property(sss_props, "string", "Name", "ServerScriptService")

    scripts_written = 0
    for script in scripts:
        si = ET.SubElement(sss_item, "Item", **{"class": script.script_type})
        sp = ET.SubElement(si, "Properties")
        _make_property(sp, "string", "Name", script.name)
        _make_property(sp, "ProtectedString", "Source", script.luau_source)
        scripts_written += 1

    xml_str = _prettify(root)
    output_path.write_text(xml_str, encoding="utf-8")

    return RbxWriteResult(
        output_path=output_path,
        parts_written=parts_written,
        scripts_written=scripts_written,
        warnings=warnings,
    )
