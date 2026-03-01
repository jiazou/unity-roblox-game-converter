"""
material_mapper.py — Parses Unity .mat files, resolves shaders and textures,
and produces Roblox-ready material definitions.

Pipeline:
  1. Build GUID → file-path map from .meta files
  2. Identify each material's shader (built-in, URP, custom, etc.)
  3. Extract ONLY the properties the shader actually reads
  4. Convert to Roblox SurfaceAppearance / BasePart properties
  5. Queue texture processing operations (channel extraction, inversion, etc.)
  6. Execute texture operations
  7. Generate UNCONVERTED.md for features that couldn't be mapped

No other module is imported here.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

import config


# ═══════════════════════════════════════════════════════════════════════════
# Data types
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ShaderInfo:
    """Metadata about a Unity shader, determined from source or known built-ins."""
    name: str
    category: str           # see _BUILTIN_SHADERS / _identify_shader
    is_transparent: bool
    uses_vertex_colors: bool
    reads_color: bool       # whether shader actually samples _Color / _BaseColor
    reads_maintex: bool
    source_path: Path | None = None

@dataclass
class TextureOperation:
    """A deferred texture-processing operation."""
    operation: str          # copy | extract_channel | invert | resize | bake_ao | threshold_alpha | pre_tile | to_grayscale
    source_path: Path
    output_filename: str
    channel: str | None = None          # R | G | B | A
    params: dict[str, Any] = field(default_factory=dict)

@dataclass
class UnconvertedFeature:
    feature_name: str
    unity_property: str
    severity: str           # LOW | MEDIUM | HIGH
    workaround: str
    auto_fixable_future: bool

@dataclass
class RobloxMaterialDef:
    """Roblox material definition ready for rbxl_writer."""
    color_map: str | None = None
    normal_map: str | None = None
    metalness_map: str | None = None
    roughness_map: str | None = None
    emissive_mask: str | None = None
    emissive_strength: float = 1.0
    emissive_tint: tuple[float, float, float] = (1.0, 1.0, 1.0)
    color_tint: tuple[float, float, float] = (1.0, 1.0, 1.0)
    alpha_mode: str = "Opaque"
    base_part_color: tuple[float, float, float] | None = None
    base_part_transparency: float = 0.0
    base_part_material: str = "SmoothPlastic"

@dataclass
class MaterialConversionResult:
    material_name: str
    material_path: Path
    shader_name: str
    pipeline: str                           # BUILTIN | URP | LEGACY | CUSTOM | PARTICLE | UNKNOWN
    roblox_def: RobloxMaterialDef | None
    texture_ops: list[TextureOperation] = field(default_factory=list)
    unconverted: list[UnconvertedFeature] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    companion_scripts: list[str] = field(default_factory=list)
    fully_converted: bool = False

@dataclass
class MaterialMapResult:
    """Top-level output of the material mapping pipeline."""
    materials: list[MaterialConversionResult] = field(default_factory=list)
    roblox_defs: dict[str, RobloxMaterialDef] = field(default_factory=dict)
    generated_textures: list[Path] = field(default_factory=list)
    unconverted_md_path: Path | None = None
    total: int = 0
    fully_converted: int = 0
    partially_converted: int = 0
    unconvertible: int = 0
    texture_ops_performed: int = 0


# ═══════════════════════════════════════════════════════════════════════════
# Step 1: GUID resolver
# ═══════════════════════════════════════════════════════════════════════════

def _build_guid_map(unity_project_path: Path) -> dict[str, Path]:
    """Scan every .meta file under Assets/, extract guid, return {guid: asset_path}."""
    guid_map: dict[str, Path] = {}
    assets_dir = unity_project_path / "Assets"
    if not assets_dir.is_dir():
        return guid_map
    for meta_path in assets_dir.rglob("*.meta"):
        try:
            text = meta_path.read_text(encoding="utf-8", errors="replace")
            for line in text.splitlines():
                if line.startswith("guid:"):
                    guid = line.split(":", 1)[1].strip()
                    asset_path = meta_path.with_suffix("")  # strip .meta
                    guid_map[guid] = asset_path
                    break
        except OSError:
            continue
    return guid_map


# ═══════════════════════════════════════════════════════════════════════════
# Step 2: Shader identifier
# ═══════════════════════════════════════════════════════════════════════════

# Known Unity built-in shader fileIDs
_BUILTIN_SHADERS: dict[int, ShaderInfo] = {
    46: ShaderInfo("Standard", "standard", False, False, True, True),
    45: ShaderInfo("Standard (Specular setup)", "standard_specular", False, False, True, True),
    10720: ShaderInfo("Legacy Shaders/Diffuse", "legacy_diffuse", False, False, True, True),
    10721: ShaderInfo("Legacy Shaders/Specular", "legacy_specular", False, False, True, True),
    10723: ShaderInfo("Legacy Shaders/Bumped Diffuse", "legacy_bumped", False, False, True, True),
    10751: ShaderInfo("Particles/Alpha Blended", "particle_alpha", True, False, False, True),
    10752: ShaderInfo("Particles/Alpha Blended Premultiply", "particle_premultiply", True, False, False, True),
    10753: ShaderInfo("Particles/Additive", "particle_additive", True, False, False, True),
    10755: ShaderInfo("Particles/Multiply", "particle_multiply", True, False, False, True),
    200: ShaderInfo("Sprites/Default", "sprite", True, False, True, True),
}

_RE_SHADER_NAME = re.compile(r'Shader\s+"([^"]+)"')
_RE_BLEND = re.compile(r"\bBlend\s+SrcAlpha\b", re.IGNORECASE)
_RE_ZWRITE_OFF = re.compile(r"\bZWrite\s+Off\b", re.IGNORECASE)
_RE_TRANSPARENT_TAG = re.compile(r'"RenderType"\s*=\s*"Transparent"', re.IGNORECASE)
_RE_VERTEX_COLOR = re.compile(r"\b[iv]\.color\b")
_RE_PROPERTIES_BLOCK = re.compile(r"Properties\s*\{([^}]*)\}", re.DOTALL)
_RE_PROPERTY_NAME = re.compile(r"(\w+)\s*\(")


def _parse_shader_source(shader_path: Path) -> ShaderInfo:
    """Parse a .shader file to determine its capabilities."""
    try:
        source = shader_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ShaderInfo("Unknown", "unknown", False, False, False, False, shader_path)

    # Shader name
    m = _RE_SHADER_NAME.search(source)
    name = m.group(1) if m else shader_path.stem

    # Transparency
    is_transparent = bool(
        _RE_BLEND.search(source)
        or _RE_ZWRITE_OFF.search(source)
        or _RE_TRANSPARENT_TAG.search(source)
    )

    # Vertex colors
    uses_vertex_colors = bool(_RE_VERTEX_COLOR.search(source))

    # Which properties does the shader declare?
    declared_props: set[str] = set()
    prop_block = _RE_PROPERTIES_BLOCK.search(source)
    if prop_block:
        for pm in _RE_PROPERTY_NAME.finditer(prop_block.group(1)):
            declared_props.add(pm.group(1))

    reads_color = "_Color" in declared_props or "_BaseColor" in declared_props
    reads_maintex = "_MainTex" in declared_props or "_BaseMap" in declared_props

    # Categorize
    name_lower = name.lower()
    if "curvedunlitalpha" in name_lower or "curvedunlitcloud" in name_lower:
        category = "custom_unlit_alpha"
    elif "curvedunlit" in name_lower:
        category = "custom_unlit"
    elif "curvedrotation" in name_lower:
        category = "custom_rotation"
    elif "unlitblinking" in name_lower:
        category = "custom_blinking"
    elif "vertexcolor" in name_lower:
        category = "vertex_color"
    elif "unlit" in name_lower:
        category = "custom_unlit"
    else:
        category = "custom"

    return ShaderInfo(name, category, is_transparent, uses_vertex_colors,
                      reads_color, reads_maintex, shader_path)


def _identify_shader(
    shader_ref: dict,
    guid_map: dict[str, Path],
    mat_properties: dict[str, Any],
) -> ShaderInfo:
    """Resolve the m_Shader reference to a ShaderInfo."""
    file_id = shader_ref.get("fileID", 0)
    guid = shader_ref.get("guid", "")

    # Built-in shader
    if file_id in _BUILTIN_SHADERS:
        return _BUILTIN_SHADERS[file_id]

    # Custom shader referenced by GUID
    if guid and guid in guid_map:
        shader_path = guid_map[guid]
        if shader_path.suffix == ".shader" and shader_path.exists():
            return _parse_shader_source(shader_path)

    # URP package shader (GUID not in Assets/) — detect by property names
    if "_BaseMap" in mat_properties or "_BaseColor" in mat_properties:
        return ShaderInfo("Universal Render Pipeline/Unlit", "urp_unlit",
                          False, False, True, True)

    return ShaderInfo("Unknown", "unknown", False, False, False, False)


# ═══════════════════════════════════════════════════════════════════════════
# Step 3: Material property extractor
# ═══════════════════════════════════════════════════════════════════════════

_UNITY_YAML_TAG_LINE = re.compile(r"^(%YAML.*|%TAG.*|--- !u!\d+ &-?\d+.*)$", re.MULTILINE)


def _clean_unity_yaml(text: str) -> str:
    """Strip Unity-specific YAML directives."""
    return _UNITY_YAML_TAG_LINE.sub("", text)


def _parse_tex_envs(raw: list | None) -> dict[str, dict]:
    """Normalize m_TexEnvs from either serializedVersion 2 or 3 format."""
    result: dict[str, dict] = {}
    if not isinstance(raw, list):
        return result
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        # v3 format: {_MainTex: {m_Texture: ..., m_Scale: ..., m_Offset: ...}}
        for key, val in entry.items():
            if key == "first":
                continue  # v2 handled below
            if isinstance(val, dict) and "m_Texture" in val:
                result[key] = val
                continue
        # v2 format: {first: {name: _MainTex}, second: {m_Texture: ..., ...}}
        if "first" in entry and "second" in entry:
            first = entry["first"]
            name = first.get("name", "") if isinstance(first, dict) else str(first)
            if name and isinstance(entry["second"], dict):
                result[name] = entry["second"]
    return result


def _parse_floats(raw: list | None) -> dict[str, float]:
    """Normalize m_Floats from either serializedVersion 2 or 3."""
    result: dict[str, float] = {}
    if not isinstance(raw, list):
        return result
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        # v3: {_Metallic: 0}
        for key, val in entry.items():
            if key == "first":
                continue
            if isinstance(val, (int, float)):
                result[key] = float(val)
        # v2: {first: {name: _Metallic}, second: 0}
        if "first" in entry and "second" in entry:
            first = entry["first"]
            name = first.get("name", "") if isinstance(first, dict) else str(first)
            if name:
                result[name] = float(entry["second"])
    return result


def _parse_colors(raw: list | None) -> dict[str, dict]:
    """Normalize m_Colors from either serializedVersion 2 or 3."""
    result: dict[str, dict] = {}
    if not isinstance(raw, list):
        return result
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        # v3: {_Color: {r: 1, g: 1, b: 1, a: 1}}
        for key, val in entry.items():
            if key == "first":
                continue
            if isinstance(val, dict) and "r" in val:
                result[key] = val
        # v2: {first: {name: _Color}, second: {r: 1, ...}}
        if "first" in entry and "second" in entry:
            first = entry["first"]
            name = first.get("name", "") if isinstance(first, dict) else str(first)
            if name and isinstance(entry["second"], dict):
                result[name] = entry["second"]
    return result


@dataclass
class ParsedMaterial:
    """Unified representation of a Unity material's active properties."""
    name: str
    path: Path
    shader: ShaderInfo
    albedo_tex_guid: str | None = None
    albedo_tex_path: Path | None = None
    albedo_tex_tiling: tuple[float, float] = (1.0, 1.0)
    albedo_tex_offset: tuple[float, float] = (0.0, 0.0)
    albedo_color: tuple[float, float, float, float] | None = None
    normal_tex_path: Path | None = None
    normal_scale: float = 1.0
    metallic_tex_path: Path | None = None
    metallic_value: float = 0.0
    smoothness_value: float = 0.5
    smoothness_source: int = 0      # 0=metallic alpha, 1=albedo alpha
    smoothness_scale: float = 1.0
    ao_tex_path: Path | None = None
    ao_strength: float = 1.0
    emission_tex_path: Path | None = None
    emission_color: tuple[float, float, float] = (0.0, 0.0, 0.0)
    render_mode: int = 0            # 0=opaque, 1=cutout, 2=fade, 3=transparent
    alpha_cutoff: float = 0.5
    tint_color: tuple[float, float, float, float] | None = None
    custom_properties: dict[str, Any] = field(default_factory=dict)


def _resolve_texture(
    tex_entry: dict,
    guid_map: dict[str, Path],
) -> tuple[str | None, Path | None]:
    """Resolve a m_TexEnvs texture reference to (guid, file_path)."""
    tex_ref = tex_entry.get("m_Texture", {})
    if not isinstance(tex_ref, dict):
        return None, None
    if tex_ref.get("fileID", 0) == 0:
        return None, None
    guid = tex_ref.get("guid", "")
    path = guid_map.get(guid)
    return guid or None, path


def _get_tiling(tex_entry: dict) -> tuple[float, float]:
    scale = tex_entry.get("m_Scale", {})
    if isinstance(scale, dict):
        return (float(scale.get("x", 1)), float(scale.get("y", 1)))
    return (1.0, 1.0)


def _get_offset(tex_entry: dict) -> tuple[float, float]:
    off = tex_entry.get("m_Offset", {})
    if isinstance(off, dict):
        return (float(off.get("x", 0)), float(off.get("y", 0)))
    return (0.0, 0.0)


def _color_to_tuple(c: dict) -> tuple[float, float, float, float]:
    return (float(c.get("r", 1)), float(c.get("g", 1)),
            float(c.get("b", 1)), float(c.get("a", 1)))


def _color_rgb(c: dict) -> tuple[float, float, float]:
    return (float(c.get("r", 0)), float(c.get("g", 0)), float(c.get("b", 0)))


def _parse_material(
    mat_path: Path,
    guid_map: dict[str, Path],
) -> ParsedMaterial | None:
    """Parse a .mat YAML file into a ParsedMaterial with shader-aware extraction."""
    try:
        raw = mat_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    cleaned = _clean_unity_yaml(raw)
    try:
        data = yaml.safe_load(cleaned)
    except yaml.YAMLError:
        return None

    if not isinstance(data, dict) or "Material" not in data:
        return None
    mat = data["Material"]
    props = mat.get("m_SavedProperties", {})

    # Parse raw property lists
    tex_envs = _parse_tex_envs(props.get("m_TexEnvs"))
    floats = _parse_floats(props.get("m_Floats"))
    colors = _parse_colors(props.get("m_Colors"))

    # Determine which property names exist (for URP detection)
    all_prop_names = set(tex_envs.keys()) | set(floats.keys()) | set(colors.keys())

    # Identify shader
    shader_ref = mat.get("m_Shader", {})
    shader = _identify_shader(shader_ref, guid_map, all_prop_names)

    parsed = ParsedMaterial(
        name=mat.get("m_Name", mat_path.stem),
        path=mat_path,
        shader=shader,
    )

    # --- Albedo texture (only if shader reads it) ---
    if shader.reads_maintex:
        # Try _MainTex first, then _BaseMap, then _BaseColorMap
        for tex_name in ("_MainTex", "_BaseMap", "_BaseColorMap"):
            if tex_name in tex_envs:
                guid, path = _resolve_texture(tex_envs[tex_name], guid_map)
                if guid:
                    parsed.albedo_tex_guid = guid
                    parsed.albedo_tex_path = path
                    parsed.albedo_tex_tiling = _get_tiling(tex_envs[tex_name])
                    parsed.albedo_tex_offset = _get_offset(tex_envs[tex_name])
                    break

    # --- Albedo color (only if shader reads it) ---
    if shader.reads_color:
        for color_name in ("_Color", "_BaseColor"):
            if color_name in colors:
                parsed.albedo_color = _color_to_tuple(colors[color_name])
                break

    # --- PBR maps (only for standard / URP lit / HDRP lit) ---
    if shader.category in ("standard", "standard_specular", "urp_lit", "hdrp_lit"):
        # Normal map
        for nm_name in ("_BumpMap", "_NormalMap"):
            if nm_name in tex_envs:
                _, path = _resolve_texture(tex_envs[nm_name], guid_map)
                if path:
                    parsed.normal_tex_path = path
                    break
        parsed.normal_scale = floats.get("_BumpScale", floats.get("_NormalScale", 1.0))

        # Metallic map
        for met_name in ("_MetallicGlossMap", "_MaskMap"):
            if met_name in tex_envs:
                _, path = _resolve_texture(tex_envs[met_name], guid_map)
                if path:
                    parsed.metallic_tex_path = path
                    break
        parsed.metallic_value = floats.get("_Metallic", 0.0)

        # Smoothness
        parsed.smoothness_value = floats.get("_Glossiness", floats.get("_Smoothness", 0.5))
        parsed.smoothness_scale = floats.get("_GlossMapScale", 1.0)
        parsed.smoothness_source = int(floats.get("_SmoothnessTextureChannel", 0))

        # Occlusion
        if "_OcclusionMap" in tex_envs:
            _, path = _resolve_texture(tex_envs["_OcclusionMap"], guid_map)
            if path:
                parsed.ao_tex_path = path
        parsed.ao_strength = floats.get("_OcclusionStrength", 1.0)

        # Emission
        keywords = mat.get("m_ShaderKeywords", "") or ""
        invalid_kw = mat.get("m_InvalidKeywords", []) or []
        emission_active = (
            "_EMISSION" in str(keywords)
            and "_EMISSION" not in (invalid_kw if isinstance(invalid_kw, list) else [])
        )
        if emission_active:
            for em_name in ("_EmissionMap", "_EmissiveColorMap"):
                if em_name in tex_envs:
                    _, path = _resolve_texture(tex_envs[em_name], guid_map)
                    if path:
                        parsed.emission_tex_path = path
                        break
            for ec_name in ("_EmissionColor", "_EmissiveColor"):
                if ec_name in colors:
                    parsed.emission_color = _color_rgb(colors[ec_name])
                    break

        # Render mode
        mode_val = floats.get("_Mode", 0)
        parsed.render_mode = int(mode_val)
        parsed.alpha_cutoff = floats.get("_Cutoff", 0.5)

    # --- Particle tint ---
    if "_TintColor" in colors:
        parsed.tint_color = _color_to_tuple(colors["_TintColor"])

    # --- Custom properties ---
    for k, v in floats.items():
        if k.startswith("_Curve") or k.startswith("_Blink") or k.startswith("_InvFade"):
            parsed.custom_properties[k] = v

    return parsed


# ═══════════════════════════════════════════════════════════════════════════
# Step 4: Material converter core
# ═══════════════════════════════════════════════════════════════════════════

def _is_white(c: tuple[float, ...], threshold: float = 0.99) -> bool:
    return all(v >= threshold for v in c[:3])


def _is_black(c: tuple[float, ...], threshold: float = 0.01) -> bool:
    return all(v <= threshold for v in c[:3])


def _color_luminance(r: float, g: float, b: float) -> float:
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _safe_filename(name: str, suffix: str) -> str:
    """Sanitize a material name into a safe filename."""
    safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", name)
    return f"{safe}{suffix}"


def _convert_material(parsed: ParsedMaterial) -> MaterialConversionResult:
    """Convert a ParsedMaterial into a Roblox material definition."""
    result = MaterialConversionResult(
        material_name=parsed.name,
        material_path=parsed.path,
        shader_name=parsed.shader.name,
        pipeline=_pipeline_label(parsed.shader.category),
        roblox_def=None,
    )

    cat = parsed.shader.category

    # --- Fully unconvertible ---
    if cat == "vertex_color":
        result.unconverted.append(UnconvertedFeature(
            "Vertex-color-only shader", "VertexColor shader",
            "HIGH", "Assign flat color manually in Roblox Studio", False,
        ))
        return result

    if cat == "unknown":
        result.unconverted.append(UnconvertedFeature(
            "Unrecognized shader", f"Shader: {parsed.shader.name}",
            "HIGH", "Manually inspect material in Unity and recreate in Roblox", False,
        ))
        return result

    # --- Build Roblox definition ---
    rdef = RobloxMaterialDef()
    mat_name = parsed.name

    # Albedo texture
    if parsed.albedo_tex_path and parsed.albedo_tex_path.exists():
        out_name = _safe_filename(mat_name, "_color.png")
        result.texture_ops.append(TextureOperation(
            "copy", parsed.albedo_tex_path, out_name,
        ))
        rdef.color_map = out_name

        # Tiling
        tx, ty = parsed.albedo_tex_tiling
        if tx != 1.0 or ty != 1.0:
            itx, ity = int(tx), int(ty)
            if 1 < max(itx, ity) <= config.PRE_TILE_MAX_FACTOR:
                result.texture_ops[-1] = TextureOperation(
                    "pre_tile", parsed.albedo_tex_path, out_name,
                    params={"tile_x": itx, "tile_y": ity},
                )
            else:
                result.unconverted.append(UnconvertedFeature(
                    f"Texture tiling ({tx}x, {ty}x)", "_MainTex_ST",
                    "HIGH", "Modify mesh UVs or pre-tile texture manually",
                    tx <= config.PRE_TILE_MAX_FACTOR and ty <= config.PRE_TILE_MAX_FACTOR,
                ))

        # Offset
        ox, oy = parsed.albedo_tex_offset
        if ox != 0.0 or oy != 0.0:
            result.texture_ops[-1].params["offset_x"] = ox
            result.texture_ops[-1].params["offset_y"] = oy

    elif parsed.albedo_color and not _is_white(parsed.albedo_color):
        # No texture, just color → BasePart.Color3
        rdef.base_part_color = parsed.albedo_color[:3]
    elif not parsed.albedo_tex_path and cat in ("standard", "standard_specular",
                                                 "urp_lit", "urp_unlit",
                                                 "legacy_diffuse"):
        # No texture, white color → default gray part
        rdef.base_part_color = (0.639, 0.635, 0.647)  # "Medium stone grey"

    # Albedo color tint (when texture IS present)
    if parsed.albedo_color and rdef.color_map and not _is_white(parsed.albedo_color):
        rdef.color_tint = parsed.albedo_color[:3]

    # Alpha from _Color
    if parsed.albedo_color and parsed.albedo_color[3] < 0.99:
        rdef.base_part_transparency = 1.0 - parsed.albedo_color[3]

    # --- PBR maps (Standard / URP Lit / HDRP Lit) ---
    if cat in ("standard", "standard_specular", "urp_lit", "hdrp_lit"):
        # Normal map
        if parsed.normal_tex_path and parsed.normal_tex_path.exists():
            nm_out = _safe_filename(mat_name, "_normal.png")
            if abs(parsed.normal_scale - 1.0) > 0.01:
                result.texture_ops.append(TextureOperation(
                    "copy", parsed.normal_tex_path, nm_out,
                    params={"bake_normal_scale": parsed.normal_scale},
                ))
                result.warnings.append(
                    f"Normal scale {parsed.normal_scale} baked into normal map"
                )
            else:
                result.texture_ops.append(TextureOperation(
                    "copy", parsed.normal_tex_path, nm_out,
                ))
            rdef.normal_map = nm_out

        # Metallic + Roughness (from packed texture)
        if parsed.metallic_tex_path and parsed.metallic_tex_path.exists():
            met_out = _safe_filename(mat_name, "_metalness.png")
            rough_out = _safe_filename(mat_name, "_roughness.png")
            result.texture_ops.append(TextureOperation(
                "extract_channel", parsed.metallic_tex_path, met_out, channel="R",
            ))
            result.texture_ops.append(TextureOperation(
                "extract_channel", parsed.metallic_tex_path, rough_out, channel="A",
                params={"invert": True, "scale": parsed.smoothness_scale},
            ))
            rdef.metalness_map = met_out
            rdef.roughness_map = rough_out
        else:
            # Scalar fallbacks — generate tiny uniform textures
            if parsed.metallic_value > 0.01:
                met_out = _safe_filename(mat_name, "_metalness.png")
                result.texture_ops.append(TextureOperation(
                    "copy", Path("__uniform__"), met_out,
                    params={"uniform_value": int(parsed.metallic_value * 255)},
                ))
                rdef.metalness_map = met_out
            # Roughness from smoothness
            roughness = 1.0 - parsed.smoothness_value
            if roughness < 0.99:
                rough_out = _safe_filename(mat_name, "_roughness.png")
                result.texture_ops.append(TextureOperation(
                    "copy", Path("__uniform__"), rough_out,
                    params={"uniform_value": int(roughness * 255)},
                ))
                rdef.roughness_map = rough_out

        # Occlusion → bake into color map
        if parsed.ao_tex_path and parsed.ao_tex_path.exists() and rdef.color_map:
            result.texture_ops.append(TextureOperation(
                "bake_ao", parsed.ao_tex_path, rdef.color_map,
                params={"albedo_path": str(parsed.albedo_tex_path),
                        "strength": parsed.ao_strength},
            ))
            result.warnings.append("Occlusion map baked into ColorMap")

        # Emission
        if parsed.emission_tex_path and parsed.emission_tex_path.exists():
            em_out = _safe_filename(mat_name, "_emissive.png")
            result.texture_ops.append(TextureOperation(
                "to_grayscale", parsed.emission_tex_path, em_out,
            ))
            rdef.emissive_mask = em_out
            ec = parsed.emission_color
            lum = _color_luminance(*ec)
            if lum > 0.01:
                rdef.emissive_tint = (ec[0] / max(lum, 0.001),
                                      ec[1] / max(lum, 0.001),
                                      ec[2] / max(lum, 0.001))
                rdef.emissive_strength = min(lum * 2.0, 10.0)
            else:
                rdef.emissive_strength = 1.0
        elif not _is_black(parsed.emission_color):
            ec = parsed.emission_color
            lum = _color_luminance(*ec)
            if lum > 0.01:
                em_out = _safe_filename(mat_name, "_emissive.png")
                result.texture_ops.append(TextureOperation(
                    "copy", Path("__uniform__"), em_out,
                    params={"uniform_value": 255},
                ))
                rdef.emissive_mask = em_out
                rdef.emissive_tint = (ec[0] / max(lum, 0.001),
                                      ec[1] / max(lum, 0.001),
                                      ec[2] / max(lum, 0.001))
                rdef.emissive_strength = min(lum * 2.0, 10.0)

        # Render mode → AlphaMode
        if parsed.render_mode == 0:
            rdef.alpha_mode = "Opaque"
        elif parsed.render_mode == 1:
            rdef.alpha_mode = "Transparency"
            if rdef.color_map and parsed.albedo_tex_path:
                result.texture_ops.append(TextureOperation(
                    "threshold_alpha", parsed.albedo_tex_path, rdef.color_map,
                    params={"cutoff": parsed.alpha_cutoff},
                ))
        else:
            rdef.alpha_mode = "Transparency"

        # Detail maps — log as unconverted
        for detail_prop in ("_DetailAlbedoMap", "_DetailNormalMap", "_DetailMask"):
            if detail_prop in _collect_tex_names(parsed):
                result.unconverted.append(UnconvertedFeature(
                    "Detail map", detail_prop, "MEDIUM",
                    "Bake detail into base texture offline", True,
                ))
                break

        # Height map — log as unconverted
        if "_ParallaxMap" in _collect_tex_names(parsed) or "_HeightMap" in _collect_tex_names(parsed):
            result.unconverted.append(UnconvertedFeature(
                "Height/parallax map", "_ParallaxMap", "MEDIUM",
                "Convert to normal map detail or bake into mesh", True,
            ))

    # --- Transparency from shader (for custom shaders) ---
    if parsed.shader.is_transparent and cat not in ("standard", "standard_specular",
                                                     "urp_lit", "hdrp_lit"):
        rdef.alpha_mode = "Transparency"

    # --- Vertex colors → unconverted ---
    if parsed.shader.uses_vertex_colors:
        result.unconverted.append(UnconvertedFeature(
            "Vertex color multiplication", "Vertex colors in shader",
            "HIGH", "Bake vertex colors into albedo texture (requires mesh data)",
            True,
        ))

    # --- Custom shader-specific unconverted features ---
    if "_CurveStrength" in parsed.custom_properties:
        result.unconverted.append(UnconvertedFeature(
            "World curve effect", "_CurveStrength",
            "LOW", "Ignore — cosmetic endless-runner effect", False,
        ))

    if cat == "custom_blinking":
        result.companion_scripts.append(_BLINK_SCRIPT)
        result.unconverted.append(UnconvertedFeature(
            "Blinking animation", "_BlinkingValue",
            "LOW", "Companion Luau tween script generated", True,
        ))

    if cat == "custom_rotation":
        result.companion_scripts.append(_ROTATION_SCRIPT)
        result.unconverted.append(UnconvertedFeature(
            "Vertex rotation animation", "_Time rotation in vertex shader",
            "LOW", "Companion Luau rotation script generated", True,
        ))

    # --- Particle-specific ---
    if cat in ("particle_alpha", "particle_premultiply", "particle_additive",
               "particle_multiply"):
        rdef.base_part_material = "SmoothPlastic"
        if parsed.tint_color and not _is_white(parsed.tint_color):
            rdef.color_tint = parsed.tint_color[:3]
        if cat == "particle_additive":
            result.unconverted.append(UnconvertedFeature(
                "Additive blending", "Particles/Additive",
                "LOW", "Use ParticleEmitter.LightEmission = 1", True,
            ))
        if cat == "particle_premultiply":
            result.unconverted.append(UnconvertedFeature(
                "Premultiplied alpha blending", "Particles/Premultiply",
                "LOW", "Use standard alpha blending (close approximation)", True,
            ))
        if "_InvFade" in parsed.custom_properties:
            result.unconverted.append(UnconvertedFeature(
                "Soft particles", "_InvFade",
                "LOW", "No Roblox equivalent — accept hard particle edges", False,
            ))

    result.roblox_def = rdef
    result.fully_converted = len(result.unconverted) == 0

    return result


def _collect_tex_names(parsed: ParsedMaterial) -> set[str]:
    """Return the set of texture property names that have non-null paths."""
    names: set[str] = set()
    # Re-read the mat file quickly to check for detail/height textures
    try:
        raw = parsed.path.read_text(encoding="utf-8", errors="replace")
        cleaned = _clean_unity_yaml(raw)
        data = yaml.safe_load(cleaned)
        if not isinstance(data, dict):
            return names
        mat = data.get("Material", {})
        props = mat.get("m_SavedProperties", {})
        tex_envs = _parse_tex_envs(props.get("m_TexEnvs"))
        for name, entry in tex_envs.items():
            tex_ref = entry.get("m_Texture", {})
            if isinstance(tex_ref, dict) and tex_ref.get("fileID", 0) != 0:
                names.add(name)
    except Exception:
        pass
    return names


def _pipeline_label(category: str) -> str:
    if category in ("standard", "standard_specular"):
        return "BUILTIN"
    if category.startswith("urp"):
        return "URP"
    if category.startswith("hdrp"):
        return "HDRP"
    if category.startswith("legacy"):
        return "LEGACY"
    if category.startswith("particle") or category == "sprite":
        return "PARTICLE"
    if category.startswith("custom") or category == "vertex_color":
        return "CUSTOM"
    return "UNKNOWN"


# Companion Luau scripts
_BLINK_SCRIPT = """\
-- Auto-generated: blinking effect (from Unity UnlitBlinking shader)
local TweenService = game:GetService("TweenService")
local part = script.Parent

local original = part.Color
local blink = Color3.new(1, 1, 0.75)
local info = TweenInfo.new(0.5, Enum.EasingStyle.Sine, Enum.EasingDirection.InOut, -1, true)
local tween = TweenService:Create(part, info, {Color = blink})
tween:Play()
"""

_ROTATION_SCRIPT = """\
-- Auto-generated: rotation effect (from Unity CurvedRotation shader)
local RunService = game:GetService("RunService")
local part = script.Parent

RunService.Heartbeat:Connect(function(dt)
    part.CFrame = part.CFrame * CFrame.Angles(0, math.pi * dt, 0)
end)
"""


# ═══════════════════════════════════════════════════════════════════════════
# Step 5: Texture processor
# ═══════════════════════════════════════════════════════════════════════════

def _process_textures(
    ops: list[TextureOperation],
    output_dir: Path,
) -> list[Path]:
    """Execute texture operations, return list of generated file paths."""
    try:
        from PIL import Image
    except ImportError:
        # Pillow not installed — skip texture processing, return empty
        return []

    output_dir.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []
    max_res = config.TEXTURE_MAX_RESOLUTION

    for op in ops:
        out_path = output_dir / op.output_filename
        try:
            if op.source_path == Path("__uniform__"):
                # Generate a uniform 4x4 texture
                val = op.params.get("uniform_value", 128)
                img = Image.new("L", (4, 4), val)
                img.save(out_path, "PNG")
                generated.append(out_path)
                continue

            if not op.source_path.exists():
                continue

            if op.operation == "copy":
                img = Image.open(op.source_path)
                # Resize if needed
                if img.width > max_res or img.height > max_res:
                    ratio = min(max_res / img.width, max_res / img.height)
                    new_size = (int(img.width * ratio), int(img.height * ratio))
                    img = img.resize(new_size, Image.LANCZOS)
                img.save(out_path, "PNG")
                generated.append(out_path)

            elif op.operation == "extract_channel":
                img = Image.open(op.source_path)
                ch_map = {"R": 0, "G": 1, "B": 2, "A": 3}
                ch_idx = ch_map.get(op.channel or "R", 0)
                bands = img.split()
                if ch_idx < len(bands):
                    ch_img = bands[ch_idx]
                else:
                    ch_img = bands[0]
                if op.params.get("invert"):
                    from PIL import ImageOps
                    ch_img = ImageOps.invert(ch_img)
                scale = op.params.get("scale", 1.0)
                if scale < 0.99:
                    ch_img = ch_img.point(lambda p: int(p * scale))
                if ch_img.width > max_res or ch_img.height > max_res:
                    ratio = min(max_res / ch_img.width, max_res / ch_img.height)
                    new_size = (int(ch_img.width * ratio), int(ch_img.height * ratio))
                    ch_img = ch_img.resize(new_size, Image.LANCZOS)
                ch_img.save(out_path, "PNG")
                generated.append(out_path)

            elif op.operation == "to_grayscale":
                img = Image.open(op.source_path).convert("L")
                if img.width > max_res or img.height > max_res:
                    ratio = min(max_res / img.width, max_res / img.height)
                    new_size = (int(img.width * ratio), int(img.height * ratio))
                    img = img.resize(new_size, Image.LANCZOS)
                img.save(out_path, "PNG")
                generated.append(out_path)

            elif op.operation == "pre_tile":
                img = Image.open(op.source_path)
                tile_x = op.params.get("tile_x", 2)
                tile_y = op.params.get("tile_y", 2)
                tiled = Image.new(img.mode, (img.width * tile_x, img.height * tile_y))
                for tx in range(tile_x):
                    for ty in range(tile_y):
                        tiled.paste(img, (tx * img.width, ty * img.height))
                if tiled.width > max_res or tiled.height > max_res:
                    ratio = min(max_res / tiled.width, max_res / tiled.height)
                    new_size = (int(tiled.width * ratio), int(tiled.height * ratio))
                    tiled = tiled.resize(new_size, Image.LANCZOS)
                tiled.save(out_path, "PNG")
                generated.append(out_path)

            elif op.operation == "threshold_alpha":
                img = Image.open(op.source_path).convert("RGBA")
                cutoff = int(op.params.get("cutoff", 0.5) * 255)
                r, g, b, a = img.split()
                a = a.point(lambda p: 255 if p >= cutoff else 0)
                img = Image.merge("RGBA", (r, g, b, a))
                if img.width > max_res or img.height > max_res:
                    ratio = min(max_res / img.width, max_res / img.height)
                    new_size = (int(img.width * ratio), int(img.height * ratio))
                    img = img.resize(new_size, Image.LANCZOS)
                img.save(out_path, "PNG")
                generated.append(out_path)

            elif op.operation == "bake_ao":
                albedo_path = Path(op.params.get("albedo_path", ""))
                strength = op.params.get("strength", 1.0)
                if not albedo_path.exists():
                    continue
                albedo = Image.open(albedo_path).convert("RGB")
                ao = Image.open(op.source_path).convert("L")
                ao = ao.resize(albedo.size, Image.LANCZOS)
                # final = albedo * lerp(1, ao, strength)
                import numpy as np
                alb_arr = np.array(albedo, dtype=np.float32)
                ao_arr = np.array(ao, dtype=np.float32) / 255.0
                factor = 1.0 - strength + strength * ao_arr[..., np.newaxis]
                result_arr = np.clip(alb_arr * factor, 0, 255).astype(np.uint8)
                Image.fromarray(result_arr).save(out_path, "PNG")
                generated.append(out_path)

        except Exception:
            # Skip individual texture failures — don't crash the pipeline
            continue

    return generated


# ═══════════════════════════════════════════════════════════════════════════
# Step 6: UNCONVERTED.md generator
# ═══════════════════════════════════════════════════════════════════════════

def _generate_unconverted_md(
    results: list[MaterialConversionResult],
    project_name: str,
    output_path: Path,
) -> Path:
    """Generate the UNCONVERTED.md Smartdown file."""
    total = len(results)
    fully = sum(1 for r in results if r.fully_converted)
    partial = sum(1 for r in results if not r.fully_converted and r.roblox_def is not None)
    skipped = sum(1 for r in results if r.roblox_def is None)

    # Aggregate unconverted features by name
    feature_counts: dict[str, list[MaterialConversionResult]] = {}
    for r in results:
        for uf in r.unconverted:
            feature_counts.setdefault(uf.feature_name, []).append(r)

    lines: list[str] = []
    w = lines.append

    w("# Unconverted Features Report")
    w("")
    w(f"> Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    w(f"> Unity Project: {project_name}")
    w("")
    w("## Conversion Statistics")
    w("")
    w("| Metric | Value |")
    w("|--------|-------|")
    w(f"| Total materials processed | {total} |")
    w(f"| Fully converted | {fully} |")
    w(f"| Partially converted | {partial} |")
    w(f"| Skipped (unconvertible) | {skipped} |")
    w("")

    if feature_counts:
        w("## Unconverted Feature Summary")
        w("")
        w("| Feature | Materials Affected | Severity |")
        w("|---------|--------------------|----------|")
        for feat_name, mats in sorted(feature_counts.items(),
                                       key=lambda x: len(x[1]), reverse=True):
            sev = mats[0].unconverted[0].severity if mats[0].unconverted else "?"
            for uf in mats[0].unconverted:
                if uf.feature_name == feat_name:
                    sev = uf.severity
                    break
            w(f"| {feat_name} | {len(mats)} | {sev} |")
        w("")

    # Per-material details (only for materials with issues)
    problem_mats = [r for r in results if r.unconverted]
    if problem_mats:
        w("## Materials Requiring Manual Work")
        w("")
        for r in sorted(problem_mats, key=lambda r: r.material_name):
            w(f"### {r.material_name} (`{r.material_path}`)")
            w("")
            w(f"**Shader**: `{r.shader_name}`  ")
            w(f"**Pipeline**: {r.pipeline}  ")
            w(f"**Status**: {'Partially converted' if r.roblox_def else 'Not converted'}")
            w("")
            if r.roblox_def:
                w("**Converted**: ", )
                if r.roblox_def.color_map:
                    w(f"- [x] Albedo texture → ColorMap (`{r.roblox_def.color_map}`)")
                if not _is_white(r.roblox_def.color_tint):
                    w(f"- [x] Color tint → SurfaceAppearance.Color {r.roblox_def.color_tint}")
                if r.roblox_def.normal_map:
                    w(f"- [x] Normal map → NormalMap (`{r.roblox_def.normal_map}`)")
                if r.roblox_def.metalness_map:
                    w(f"- [x] Metalness → MetalnessMap (`{r.roblox_def.metalness_map}`)")
                if r.roblox_def.roughness_map:
                    w(f"- [x] Roughness → RoughnessMap (`{r.roblox_def.roughness_map}`)")
                if r.roblox_def.emissive_mask:
                    w(f"- [x] Emission → EmissiveMask (`{r.roblox_def.emissive_mask}`)")
                if r.roblox_def.alpha_mode != "Opaque":
                    w(f"- [x] Alpha mode → {r.roblox_def.alpha_mode}")
                w("")
            w("**Unconverted**:")
            for uf in r.unconverted:
                w(f"- [ ] **{uf.feature_name}** ({uf.severity}) — {uf.workaround}")
            w("")
            if r.companion_scripts:
                w(f"**Companion scripts**: {len(r.companion_scripts)} Luau script(s) generated")
                w("")
            w("---")
            w("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


# ═══════════════════════════════════════════════════════════════════════════
# Step 7: Public API
# ═══════════════════════════════════════════════════════════════════════════

def map_materials(
    unity_project_path: str | Path,
    output_dir: str | Path,
) -> MaterialMapResult:
    """
    Parse all .mat files in a Unity project, convert to Roblox material
    definitions, process textures, and generate UNCONVERTED.md.

    Args:
        unity_project_path: Root of the Unity project (contains Assets/).
        output_dir: Where to write generated textures and UNCONVERTED.md.

    Returns:
        MaterialMapResult with all conversion results and aggregate stats.
    """
    unity_path = Path(unity_project_path).resolve()
    out_dir = Path(output_dir).resolve()
    textures_dir = out_dir / "textures"

    # 1. Build GUID map
    guid_map = _build_guid_map(unity_path)

    # 2–4. Parse and convert each .mat file
    assets_dir = unity_path / "Assets"
    results: list[MaterialConversionResult] = []
    all_tex_ops: list[TextureOperation] = []

    if assets_dir.is_dir():
        for mat_path in sorted(assets_dir.rglob("*.mat")):
            parsed = _parse_material(mat_path, guid_map)
            if parsed is None:
                results.append(MaterialConversionResult(
                    material_name=mat_path.stem,
                    material_path=mat_path,
                    shader_name="<parse error>",
                    pipeline="UNKNOWN",
                    roblox_def=None,
                    warnings=[f"Failed to parse {mat_path.name}"],
                ))
                continue
            converted = _convert_material(parsed)
            results.append(converted)
            all_tex_ops.extend(converted.texture_ops)

    # 5. Process textures
    generated = _process_textures(all_tex_ops, textures_dir)

    # 6. Generate UNCONVERTED.md
    unconverted_path = out_dir / config.UNCONVERTED_FILENAME
    _generate_unconverted_md(results, unity_path.name, unconverted_path)

    # Build result
    roblox_defs = {}
    for r in results:
        if r.roblox_def:
            roblox_defs[r.material_name] = r.roblox_def

    total = len(results)
    fully = sum(1 for r in results if r.fully_converted)
    partial = sum(1 for r in results if not r.fully_converted and r.roblox_def is not None)
    unconvertible = sum(1 for r in results if r.roblox_def is None)

    return MaterialMapResult(
        materials=results,
        roblox_defs=roblox_defs,
        generated_textures=generated,
        unconverted_md_path=unconverted_path,
        total=total,
        fully_converted=fully,
        partially_converted=partial,
        unconvertible=unconvertible,
        texture_ops_performed=len(generated),
    )
