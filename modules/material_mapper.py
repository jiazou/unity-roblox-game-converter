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
    operation: str          # copy | extract_channel | invert | resize | bake_ao | threshold_alpha | pre_tile | to_grayscale | composite_detail | blend_normal_detail | heightmap_to_normal
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
    roblox_defs: dict[Path, RobloxMaterialDef] = field(default_factory=dict)
    companion_scripts: dict[Path, list[str]] = field(default_factory=dict)
    generated_textures: list[Path] = field(default_factory=list)
    unconverted_md_path: Path | None = None
    total: int = 0
    fully_converted: int = 0
    partially_converted: int = 0
    unconvertible: int = 0
    texture_ops_performed: int = 0
    warnings: list[str] = field(default_factory=list)


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
    # Additional common built-in shaders
    10750: ShaderInfo("UI/Default", "ui_default", True, False, True, True),
    10703: ShaderInfo("Legacy Shaders/Transparent/Diffuse", "legacy_transparent_diffuse", True, False, True, True),
    10704: ShaderInfo("Legacy Shaders/Transparent/Specular", "legacy_transparent_specular", True, False, True, True),
    10707: ShaderInfo("Legacy Shaders/Self-Illumin/Diffuse", "legacy_self_illumin", False, False, True, True),
    10701: ShaderInfo("Unlit/Texture", "unlit_texture", False, False, False, True),
    10700: ShaderInfo("Unlit/Color", "unlit_color", False, False, True, False),
    10702: ShaderInfo("Unlit/Transparent", "unlit_transparent", True, False, False, True),
    10710: ShaderInfo("Mobile/Diffuse", "mobile_diffuse", False, False, True, True),
    10760: ShaderInfo("Skybox/6 Sided", "skybox_6sided", False, False, False, True),
    10770: ShaderInfo("Skybox/Procedural", "skybox_procedural", False, False, False, False),
}

_RE_SHADER_NAME = re.compile(r'Shader\s+"([^"]+)"')
_RE_BLEND = re.compile(r"\bBlend\s+SrcAlpha\b", re.IGNORECASE)
_RE_ZWRITE_OFF = re.compile(r"\bZWrite\s+Off\b", re.IGNORECASE)
_RE_TRANSPARENT_TAG = re.compile(r'"RenderType"\s*=\s*"Transparent"', re.IGNORECASE)
_RE_VERTEX_COLOR = re.compile(r"\b[iv]\.color\b")
_RE_PROPERTIES_BLOCK = re.compile(r"Properties\s*\{([^}]*)\}", re.DOTALL)
_RE_PROPERTY_NAME = re.compile(r"(\w+)\s*\(")


_RE_INCLUDE = re.compile(r'#include\s+"([^"]+)"')


# ---------------------------------------------------------------------------
# Data-driven custom shader classification
# ---------------------------------------------------------------------------
# Each entry is (list_of_substrings, category).  The shader name is lowercased
# and checked against the substrings in order — first match wins.  This makes
# it easy to add project-specific shaders without touching control flow.

_CUSTOM_SHADER_PATTERNS: list[tuple[list[str], str]] = [
    (["curvedunlitalpha", "curvedunlitcloud"], "custom_unlit_alpha"),
    (["curvedunlit"],                          "custom_unlit"),
    (["curvedrotation"],                       "custom_rotation"),
    (["unlitblinking"],                        "custom_blinking"),
    (["vertexcolor"],                          "vertex_color"),
    (["unlit"],                                "custom_unlit"),
]


def _classify_custom_shader(shader_name: str) -> str:
    """Classify a custom shader name into a category via pattern matching."""
    name_lower = shader_name.lower()
    for patterns, category in _CUSTOM_SHADER_PATTERNS:
        if any(p in name_lower for p in patterns):
            return category
    return "custom"


# ---------------------------------------------------------------------------
# Companion script registry — maps shader categories to Luau scripts
# ---------------------------------------------------------------------------
# Instead of hardcoded if/elif blocks in the conversion function, companion
# scripts are registered here by category.  The conversion function looks up
# scripts via this mapping.

_COMPANION_SCRIPTS: dict[str, str] = {}  # populated below, after script definitions


def _parse_shader_source(shader_path: Path) -> ShaderInfo:
    """Parse a .shader file to determine its capabilities."""
    try:
        source = shader_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        # Can't read source — be conservative: assume shader uses color and texture
        return ShaderInfo("Unknown", "unknown", False, False, True, True, shader_path)

    # Resolve local #include files (.cginc / .hlsl) in the same directory tree
    # so property and feature detection covers the full shader program.
    full_source = source
    shader_dir = shader_path.parent
    for inc_match in _RE_INCLUDE.finditer(source):
        inc_name = inc_match.group(1)
        inc_path = shader_dir / inc_name
        if inc_path.exists():
            try:
                full_source += "\n" + inc_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass

    # Shader name
    m = _RE_SHADER_NAME.search(source)
    name = m.group(1) if m else shader_path.stem

    # Transparency (search full source including includes)
    is_transparent = bool(
        _RE_BLEND.search(full_source)
        or _RE_ZWRITE_OFF.search(full_source)
        or _RE_TRANSPARENT_TAG.search(full_source)
    )

    # Vertex colors (search full source including includes)
    uses_vertex_colors = bool(_RE_VERTEX_COLOR.search(full_source))

    # Determine which properties the shader uses.
    #
    # The Properties {} block only declares what the Inspector exposes — it
    # does NOT reliably indicate what the compiled shader passes actually
    # sample.  A property can be read without being declared (set via script)
    # and a declared property can go unused.
    #
    # Strategy: search the ENTIRE source (including resolved #includes) for
    # references to the property name.  This catches both declared properties
    # and direct CG/HLSL references.  Default to True (conservative) when
    # the source is too short or obfuscated to tell.
    source_has = lambda kw: kw in full_source  # noqa: E731

    reads_color = (
        source_has("_Color") or source_has("_BaseColor")
    )
    reads_maintex = (
        source_has("_MainTex") or source_has("_BaseMap") or source_has("_BaseColorMap")
    )

    # If the source is suspiciously short (e.g. UsePass / Fallback only),
    # we can't rule anything out — default to conservative.
    if len(full_source) < 200:
        reads_color = True
        reads_maintex = True

    # Categorize via data-driven pattern matching.
    # Each entry is (patterns, category) — first match wins.
    # Patterns are matched against the lowercased shader name.
    category = _classify_custom_shader(name)

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

    # HDRP package shader — detect by HDRP-specific property names
    if "_BaseColorMap" in mat_properties or "_MaskMap" in mat_properties:
        has_hdrp = bool(
            mat_properties & {
                "_BaseColorMap", "_MaskMap", "_NormalMap",
                "_EmissiveColorMap", "_NormalScale", "_HeightMap",
            }
        )
        if has_hdrp:
            return ShaderInfo("HDRP/Lit", "hdrp_lit",
                              False, False, True, True)

    # URP package shader (GUID not in Assets/) — detect by property names
    if "_BaseMap" in mat_properties or "_BaseColor" in mat_properties:
        # Distinguish URP/Lit (has PBR properties) from URP/Unlit
        has_pbr = bool(
            mat_properties & {
                "_MetallicGlossMap", "_BumpMap", "_Metallic",
                "_Smoothness", "_OcclusionMap", "_EmissionMap",
            }
        )
        if has_pbr:
            return ShaderInfo("Universal Render Pipeline/Lit", "urp_lit",
                              False, False, True, True)
        return ShaderInfo("Universal Render Pipeline/Unlit", "urp_unlit",
                          False, False, True, True)

    # Completely unresolved shader — be conservative: assume it reads everything
    return ShaderInfo("Unknown", "unknown", False, False, True, True)


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
    specular_color: tuple[float, float, float] | None = None  # for Specular workflow
    specular_tex_path: Path | None = None  # _SpecGlossMap
    hdrp_mask_map_path: Path | None = None  # HDRP _MaskMap (MODS packing)
    detail_albedo_tex_path: Path | None = None   # _DetailAlbedoMap
    detail_normal_tex_path: Path | None = None   # _DetailNormalMapScale
    detail_mask_tex_path: Path | None = None     # _DetailMask
    detail_normal_scale: float = 1.0             # _DetailNormalMapScale
    detail_tiling: tuple[float, float] = (1.0, 1.0)  # _DetailAlbedoMap tiling
    height_tex_path: Path | None = None          # _ParallaxMap / _HeightMap
    height_strength: float = 0.02                # _Parallax / _HeightAmplitude
    active_tex_names: set[str] = field(default_factory=set)  # texture props with non-null refs


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

    # Collect texture property names that have non-null texture refs
    active_textures: set[str] = set()
    for tname, tentry in tex_envs.items():
        tex_ref = tentry.get("m_Texture", {})
        if isinstance(tex_ref, dict) and tex_ref.get("fileID", 0) != 0:
            active_textures.add(tname)

    parsed = ParsedMaterial(
        name=mat.get("m_Name", mat_path.stem),
        path=mat_path,
        shader=shader,
        active_tex_names=active_textures,
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

    # --- PBR maps (standard / standard_specular / URP lit / HDRP lit / legacy bumped/specular) ---
    pbr_categories = ("standard", "standard_specular", "urp_lit", "hdrp_lit",
                      "legacy_bumped", "legacy_specular")
    if shader.category in pbr_categories:
        # Normal map
        for nm_name in ("_BumpMap", "_NormalMap"):
            if nm_name in tex_envs:
                _, path = _resolve_texture(tex_envs[nm_name], guid_map)
                if path:
                    parsed.normal_tex_path = path
                    break
        parsed.normal_scale = floats.get("_BumpScale", floats.get("_NormalScale", 1.0))

        # Metallic map (Standard / URP) or MaskMap (HDRP)
        if shader.category == "hdrp_lit" and "_MaskMap" in tex_envs:
            # HDRP uses MODS packing: R=Metallic, G=AO, B=Detail, A=Smoothness
            _, path = _resolve_texture(tex_envs["_MaskMap"], guid_map)
            if path:
                parsed.metallic_tex_path = path
                parsed.hdrp_mask_map_path = path
                # HDRP AO is in the G channel of MaskMap — no separate _OcclusionMap
                parsed.ao_tex_path = path  # will be extracted differently in converter
        else:
            for met_name in ("_MetallicGlossMap",):
                if met_name in tex_envs:
                    _, path = _resolve_texture(tex_envs[met_name], guid_map)
                    if path:
                        parsed.metallic_tex_path = path
                        break
        parsed.metallic_value = floats.get("_Metallic", 0.0)

        # Specular workflow (Standard Specular)
        if shader.category == "standard_specular":
            if "_SpecColor" in colors:
                sc = colors["_SpecColor"]
                parsed.specular_color = _color_rgb(sc)
            if "_SpecGlossMap" in tex_envs:
                _, path = _resolve_texture(tex_envs["_SpecGlossMap"], guid_map)
                if path:
                    parsed.specular_tex_path = path
        elif shader.category == "legacy_specular":
            if "_SpecColor" in colors:
                sc = colors["_SpecColor"]
                parsed.specular_color = _color_rgb(sc)

        # Smoothness
        parsed.smoothness_value = floats.get(
            "_Glossiness", floats.get("_Smoothness", 0.5))
        parsed.smoothness_scale = floats.get(
            "_GlossMapScale", floats.get("_SmoothnessRemapMax", 1.0))
        parsed.smoothness_source = int(floats.get("_SmoothnessTextureChannel", 0))
        # HDRP always uses MaskMap A channel for smoothness
        if shader.category == "hdrp_lit":
            parsed.smoothness_source = 0  # MaskMap A, treated like metallic alpha

        # Legacy shininess → smoothness approximation
        if shader.category == "legacy_specular" and "_Shininess" in floats:
            shininess = floats["_Shininess"]
            parsed.smoothness_value = math.sqrt(max(0, min(1, shininess)))

        # Occlusion (non-HDRP; HDRP AO was already set above from MaskMap G)
        if shader.category != "hdrp_lit":
            if "_OcclusionMap" in tex_envs:
                _, path = _resolve_texture(tex_envs["_OcclusionMap"], guid_map)
                if path:
                    parsed.ao_tex_path = path
        parsed.ao_strength = floats.get(
            "_OcclusionStrength", floats.get("_AORemapMax", 1.0))

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

        # Detail maps
        for dm_name in ("_DetailAlbedoMap",):
            if dm_name in tex_envs:
                _, path = _resolve_texture(tex_envs[dm_name], guid_map)
                if path:
                    parsed.detail_albedo_tex_path = path
                    parsed.detail_tiling = _get_tiling(tex_envs[dm_name])
                break
        for dnm_name in ("_DetailNormalMap",):
            if dnm_name in tex_envs:
                _, path = _resolve_texture(tex_envs[dnm_name], guid_map)
                if path:
                    parsed.detail_normal_tex_path = path
                break
        if "_DetailMask" in tex_envs:
            _, path = _resolve_texture(tex_envs["_DetailMask"], guid_map)
            if path:
                parsed.detail_mask_tex_path = path
        parsed.detail_normal_scale = floats.get("_DetailNormalMapScale", 1.0)

        # Height / parallax map
        for hm_name in ("_ParallaxMap", "_HeightMap"):
            if hm_name in tex_envs:
                _, path = _resolve_texture(tex_envs[hm_name], guid_map)
                if path:
                    parsed.height_tex_path = path
                    break
        parsed.height_strength = floats.get(
            "_Parallax", floats.get("_HeightAmplitude", 0.02))

        # Render mode — handle both Built-in (_Mode) and URP (_Surface + _AlphaClip)
        if "_Mode" in floats:
            parsed.render_mode = int(floats["_Mode"])
        elif "_Surface" in floats:
            # URP: _Surface=0 → Opaque, _Surface=1 + _AlphaClip=0 → Fade,
            #       _Surface=1 + _AlphaClip=1 → Cutout
            surface = int(floats["_Surface"])
            alpha_clip = int(floats.get("_AlphaClip", 0))
            if surface == 0:
                parsed.render_mode = 0  # Opaque
            elif alpha_clip:
                parsed.render_mode = 1  # Cutout
            else:
                parsed.render_mode = 2  # Fade (transparent)
        else:
            parsed.render_mode = 0
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
                                                 "urp_lit", "urp_unlit", "hdrp_lit",
                                                 "legacy_diffuse", "legacy_bumped",
                                                 "legacy_specular"):
        # No texture, white color → default gray part
        rdef.base_part_color = (0.639, 0.635, 0.647)  # "Medium stone grey"

    # Albedo color tint (when texture IS present)
    if parsed.albedo_color and rdef.color_map and not _is_white(parsed.albedo_color):
        rdef.color_tint = parsed.albedo_color[:3]

    # Alpha from _Color
    if parsed.albedo_color and parsed.albedo_color[3] < 0.99:
        rdef.base_part_transparency = 1.0 - parsed.albedo_color[3]

    # --- PBR maps (Standard / Standard Specular / URP Lit / HDRP Lit / Legacy Bumped/Specular) ---
    pbr_cats = ("standard", "standard_specular", "urp_lit", "hdrp_lit",
                "legacy_bumped", "legacy_specular")
    if cat in pbr_cats:
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

        # --- Specular → Metallic conversion (Standard Specular / Legacy Specular) ---
        if cat in ("standard_specular", "legacy_specular") and parsed.specular_color:
            sc = parsed.specular_color
            spec_lum = _color_luminance(*sc)
            # Continuous mapping: preserves gradients instead of binary threshold
            estimated_metallic = max(0.0, min(1.0, spec_lum * 2.0 - 0.5))
            if estimated_metallic > 0.5 and not rdef.color_map:
                # For metals, specular color IS the albedo
                rdef.base_part_color = sc
            # Generate uniform metalness from the heuristic
            met_out = _safe_filename(mat_name, "_metalness.png")
            result.texture_ops.append(TextureOperation(
                "copy", Path("__uniform__"), met_out,
                params={"uniform_value": int(estimated_metallic * 255)},
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
            result.warnings.append(
                f"Specular→Metallic approximation (luminance={spec_lum:.2f}→metallic={estimated_metallic})"
            )

        # --- HDRP MaskMap MODS packing (R=Metal, G=AO, B=Detail, A=Smooth) ---
        elif cat == "hdrp_lit" and parsed.hdrp_mask_map_path and parsed.hdrp_mask_map_path.exists():
            met_out = _safe_filename(mat_name, "_metalness.png")
            rough_out = _safe_filename(mat_name, "_roughness.png")
            # R channel → Metalness
            result.texture_ops.append(TextureOperation(
                "extract_channel", parsed.hdrp_mask_map_path, met_out, channel="R",
            ))
            # A channel → invert → Roughness
            result.texture_ops.append(TextureOperation(
                "extract_channel", parsed.hdrp_mask_map_path, rough_out, channel="A",
                params={"invert": True, "scale": parsed.smoothness_scale},
            ))
            rdef.metalness_map = met_out
            rdef.roughness_map = rough_out

        # --- Standard Metallic + Roughness (from packed texture) ---
        elif parsed.metallic_tex_path and parsed.metallic_tex_path.exists():
            met_out = _safe_filename(mat_name, "_metalness.png")
            rough_out = _safe_filename(mat_name, "_roughness.png")
            result.texture_ops.append(TextureOperation(
                "extract_channel", parsed.metallic_tex_path, met_out, channel="R",
            ))
            # Smoothness from albedo alpha when _SmoothnessTextureChannel == 1
            if parsed.smoothness_source == 1 and parsed.albedo_tex_path and parsed.albedo_tex_path.exists():
                result.texture_ops.append(TextureOperation(
                    "extract_channel", parsed.albedo_tex_path, rough_out, channel="A",
                    params={"invert": True, "scale": parsed.smoothness_scale},
                ))
                result.warnings.append("Smoothness extracted from albedo alpha channel")
            else:
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
        # For HDRP, extract G channel from MaskMap for AO
        if cat == "hdrp_lit" and parsed.hdrp_mask_map_path and parsed.hdrp_mask_map_path.exists() and rdef.color_map:
            ao_out = _safe_filename(mat_name, "_ao_temp.png")
            result.texture_ops.append(TextureOperation(
                "extract_channel", parsed.hdrp_mask_map_path, ao_out, channel="G",
            ))
            result.texture_ops.append(TextureOperation(
                "bake_ao", Path(ao_out), rdef.color_map,
                params={"albedo_path": str(parsed.albedo_tex_path),
                        "strength": parsed.ao_strength},
            ))
            result.warnings.append("HDRP MaskMap G-channel AO baked into ColorMap")
        elif parsed.ao_tex_path and parsed.ao_tex_path.exists() and rdef.color_map:
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

        # Detail albedo map → composite into base albedo
        if parsed.detail_albedo_tex_path and parsed.detail_albedo_tex_path.exists() and rdef.color_map:
            result.texture_ops.append(TextureOperation(
                "composite_detail", parsed.detail_albedo_tex_path, rdef.color_map,
                params={
                    "base_path": str(parsed.albedo_tex_path) if parsed.albedo_tex_path else "",
                    "mask_path": str(parsed.detail_mask_tex_path) if parsed.detail_mask_tex_path else "",
                    "detail_tiling_x": parsed.detail_tiling[0],
                    "detail_tiling_y": parsed.detail_tiling[1],
                },
            ))
            result.warnings.append("Detail albedo composited into ColorMap")
        elif "_DetailAlbedoMap" in parsed.active_tex_names:
            result.unconverted.append(UnconvertedFeature(
                "Detail albedo map", "_DetailAlbedoMap", "MEDIUM",
                "Detail map exists but base albedo missing — composite skipped", True,
            ))

        # Detail normal map → blend into base normal
        if parsed.detail_normal_tex_path and parsed.detail_normal_tex_path.exists() and rdef.normal_map:
            result.texture_ops.append(TextureOperation(
                "blend_normal_detail", parsed.detail_normal_tex_path, rdef.normal_map,
                params={
                    "base_path": str(parsed.normal_tex_path) if parsed.normal_tex_path else "",
                    "mask_path": str(parsed.detail_mask_tex_path) if parsed.detail_mask_tex_path else "",
                    "detail_tiling_x": parsed.detail_tiling[0],
                    "detail_tiling_y": parsed.detail_tiling[1],
                    "detail_normal_scale": parsed.detail_normal_scale,
                },
            ))
            result.warnings.append("Detail normal blended into NormalMap")
        elif "_DetailNormalMap" in parsed.active_tex_names:
            result.unconverted.append(UnconvertedFeature(
                "Detail normal map", "_DetailNormalMap", "MEDIUM",
                "Detail normal exists but base normal missing — blend skipped", True,
            ))

        # Height/parallax map → convert to additional normal detail
        if parsed.height_tex_path and parsed.height_tex_path.exists():
            if rdef.normal_map:
                # Blend heightmap-derived normals into existing normal map
                result.texture_ops.append(TextureOperation(
                    "heightmap_to_normal", parsed.height_tex_path, rdef.normal_map,
                    params={
                        "base_normal_path": str(parsed.normal_tex_path) if parsed.normal_tex_path else "",
                        "strength": parsed.height_strength,
                    },
                ))
                result.warnings.append("Height map converted to normal detail and blended into NormalMap")
            else:
                # No existing normal map — generate one from heightmap
                nm_out = _safe_filename(mat_name, "_normal.png")
                result.texture_ops.append(TextureOperation(
                    "heightmap_to_normal", parsed.height_tex_path, nm_out,
                    params={"strength": parsed.height_strength},
                ))
                rdef.normal_map = nm_out
                result.warnings.append("Normal map generated from height map")
        elif "_ParallaxMap" in parsed.active_tex_names or "_HeightMap" in parsed.active_tex_names:
            result.unconverted.append(UnconvertedFeature(
                "Height/parallax map", "_ParallaxMap", "MEDIUM",
                "Height map referenced but texture file not resolved", True,
            ))

    # --- Transparency from shader (for custom shaders) ---
    if parsed.shader.is_transparent and cat not in pbr_cats:
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
            "LOW", "Ignore — cosmetic world-curve effect", False,
        ))

    # Look up companion scripts from the registry (data-driven)
    companion = _COMPANION_SCRIPTS.get(cat)
    if companion:
        result.companion_scripts.append(companion)

    # Record unconverted features for categories with companion scripts
    if cat == "custom_blinking":
        result.unconverted.append(UnconvertedFeature(
            "Blinking animation", "_BlinkingValue",
            "LOW", "Companion Luau tween script generated", True,
        ))

    if cat == "custom_rotation":
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

# Populate the companion script registry
_COMPANION_SCRIPTS["custom_blinking"] = _BLINK_SCRIPT
_COMPANION_SCRIPTS["custom_rotation"] = _ROTATION_SCRIPT


# ═══════════════════════════════════════════════════════════════════════════
# Step 5: Texture processor
# ═══════════════════════════════════════════════════════════════════════════

def _process_textures(
    ops: list[TextureOperation],
    output_dir: Path,
) -> tuple[list[Path], list[str]]:
    """Execute texture operations, return (generated file paths, warnings)."""
    warnings: list[str] = []
    try:
        from PIL import Image
    except ImportError:
        warnings.append(
            "Pillow (PIL) not installed — texture processing skipped. "
            "Install with: pip install Pillow"
        )
        return [], warnings

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
                # Bake normal map scale if requested (scale XY, renormalize)
                bump_scale = op.params.get("bake_normal_scale")
                if bump_scale is not None and abs(bump_scale - 1.0) > 0.01:
                    import numpy as np
                    img = img.convert("RGB")
                    arr = np.array(img, dtype=np.float32)
                    # Decode to [-1, 1]
                    nx = (arr[..., 0] / 127.5 - 1.0) * bump_scale
                    ny = (arr[..., 1] / 127.5 - 1.0) * bump_scale
                    nz = arr[..., 2] / 127.5 - 1.0
                    # Renormalize
                    length = np.sqrt(nx*nx + ny*ny + nz*nz)
                    length = np.maximum(length, 1e-6)
                    nx /= length
                    ny /= length
                    nz /= length
                    # Encode back to [0, 255]
                    arr[..., 0] = np.clip((nx + 1.0) * 127.5, 0, 255)
                    arr[..., 1] = np.clip((ny + 1.0) * 127.5, 0, 255)
                    arr[..., 2] = np.clip((nz + 1.0) * 127.5, 0, 255)
                    img = Image.fromarray(arr.astype(np.uint8))
                # Handle texture offset (pixel shift)
                offset_x = op.params.get("offset_x", 0.0)
                offset_y = op.params.get("offset_y", 0.0)
                if offset_x != 0.0 or offset_y != 0.0:
                    from PIL import ImageChops
                    shift_x = int(offset_x * img.width) % img.width
                    shift_y = int(offset_y * img.height) % img.height
                    if shift_x or shift_y:
                        img = ImageChops.offset(img, shift_x, shift_y)
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
                # Handle texture offset after tiling
                offset_x = op.params.get("offset_x", 0.0)
                offset_y = op.params.get("offset_y", 0.0)
                if offset_x != 0.0 or offset_y != 0.0:
                    from PIL import ImageChops
                    shift_x = int(offset_x * tiled.width) % tiled.width
                    shift_y = int(offset_y * tiled.height) % tiled.height
                    if shift_x or shift_y:
                        tiled = ImageChops.offset(tiled, shift_x, shift_y)
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

            elif op.operation == "composite_detail":
                # Composite detail albedo into base albedo using Unity's
                # overlay blend: result = base * (detail * 2).  Detail maps
                # are expected to be centred on 0.5 grey.
                import numpy as np
                base_path = Path(op.params.get("base_path", ""))
                mask_path_str = op.params.get("mask_path", "")
                tile_x = max(1, int(op.params.get("detail_tiling_x", 1)))
                tile_y = max(1, int(op.params.get("detail_tiling_y", 1)))

                if not base_path.exists():
                    continue
                base = Image.open(base_path).convert("RGB")
                detail = Image.open(op.source_path).convert("RGB")

                # Pre-tile detail map to match base UV space
                if tile_x > 1 or tile_y > 1:
                    tw = detail.width * tile_x
                    th = detail.height * tile_y
                    tiled = Image.new("RGB", (tw, th))
                    for tx in range(tile_x):
                        for ty in range(tile_y):
                            tiled.paste(detail, (tx * detail.width, ty * detail.height))
                    detail = tiled

                detail = detail.resize(base.size, Image.LANCZOS)

                base_arr = np.array(base, dtype=np.float32) / 255.0
                det_arr = np.array(detail, dtype=np.float32) / 255.0

                # Unity overlay blend: base < 0.5 → 2*base*detail,
                #                      base >= 0.5 → 1 - 2*(1-base)*(1-detail)
                low = 2.0 * base_arr * det_arr
                high = 1.0 - 2.0 * (1.0 - base_arr) * (1.0 - det_arr)
                blended = np.where(base_arr < 0.5, low, high)

                # Apply detail mask if present (R channel = blend weight)
                if mask_path_str:
                    mask_path = Path(mask_path_str)
                    if mask_path.exists():
                        mask = Image.open(mask_path).convert("L")
                        mask = mask.resize(base.size, Image.LANCZOS)
                        mask_arr = np.array(mask, dtype=np.float32) / 255.0
                        blended = base_arr + (blended - base_arr) * mask_arr[..., np.newaxis]

                result_arr = np.clip(blended * 255.0, 0, 255).astype(np.uint8)
                Image.fromarray(result_arr).save(out_path, "PNG")
                generated.append(out_path)

            elif op.operation == "blend_normal_detail":
                # Blend detail normal map into base normal using UDN
                # (Unreal Derivative Normal) blending:
                #   result.xy = base.xy + detail.xy
                #   result.z  = base.z
                #   normalize
                import numpy as np
                base_path = Path(op.params.get("base_path", ""))
                mask_path_str = op.params.get("mask_path", "")
                tile_x = max(1, int(op.params.get("detail_tiling_x", 1)))
                tile_y = max(1, int(op.params.get("detail_tiling_y", 1)))
                detail_scale = op.params.get("detail_normal_scale", 1.0)

                if not base_path.exists():
                    continue
                base = Image.open(base_path).convert("RGB")
                detail = Image.open(op.source_path).convert("RGB")

                # Pre-tile detail
                if tile_x > 1 or tile_y > 1:
                    tw = detail.width * tile_x
                    th = detail.height * tile_y
                    tiled = Image.new("RGB", (tw, th))
                    for tx in range(tile_x):
                        for ty in range(tile_y):
                            tiled.paste(detail, (tx * detail.width, ty * detail.height))
                    detail = tiled

                detail = detail.resize(base.size, Image.LANCZOS)

                base_arr = np.array(base, dtype=np.float32)
                det_arr = np.array(detail, dtype=np.float32)

                # Decode from [0,255] to [-1,1]
                bx = base_arr[..., 0] / 127.5 - 1.0
                by = base_arr[..., 1] / 127.5 - 1.0
                bz = base_arr[..., 2] / 127.5 - 1.0
                dx = (det_arr[..., 0] / 127.5 - 1.0) * detail_scale
                dy = (det_arr[..., 1] / 127.5 - 1.0) * detail_scale

                # Apply mask if present
                if mask_path_str:
                    mask_path = Path(mask_path_str)
                    if mask_path.exists():
                        mask = Image.open(mask_path).convert("L")
                        mask = mask.resize(base.size, Image.LANCZOS)
                        mask_arr = np.array(mask, dtype=np.float32) / 255.0
                        dx *= mask_arr
                        dy *= mask_arr

                # UDN blend
                rx = bx + dx
                ry = by + dy
                rz = bz  # keep base Z
                length = np.sqrt(rx*rx + ry*ry + rz*rz)
                length = np.maximum(length, 1e-6)
                rx /= length
                ry /= length
                rz /= length

                # Encode back to [0,255]
                out_arr = np.zeros_like(base_arr)
                out_arr[..., 0] = np.clip((rx + 1.0) * 127.5, 0, 255)
                out_arr[..., 1] = np.clip((ry + 1.0) * 127.5, 0, 255)
                out_arr[..., 2] = np.clip((rz + 1.0) * 127.5, 0, 255)
                Image.fromarray(out_arr.astype(np.uint8)).save(out_path, "PNG")
                generated.append(out_path)

            elif op.operation == "heightmap_to_normal":
                # Convert a heightmap to normal map detail using Sobel
                # filter, then optionally blend into an existing normal.
                import numpy as np
                strength = op.params.get("strength", 0.02)
                base_normal_path_str = op.params.get("base_normal_path", "")

                hmap = Image.open(op.source_path).convert("L")
                h_arr = np.array(hmap, dtype=np.float32) / 255.0

                # Sobel kernels for X and Y gradients
                # Pad edges by wrapping
                padded = np.pad(h_arr, 1, mode="wrap")
                # Sobel X: [-1 0 1; -2 0 2; -1 0 1]
                sx = (
                    -padded[:-2, :-2] + padded[:-2, 2:]
                    - 2.0 * padded[1:-1, :-2] + 2.0 * padded[1:-1, 2:]
                    - padded[2:, :-2] + padded[2:, 2:]
                )
                # Sobel Y: [-1 -2 -1; 0 0 0; 1 2 1]
                sy = (
                    -padded[:-2, :-2] - 2.0 * padded[:-2, 1:-1] - padded[:-2, 2:]
                    + padded[2:, :-2] + 2.0 * padded[2:, 1:-1] + padded[2:, 2:]
                )

                # Scale strength (parallax values are typically 0.02-0.1,
                # multiply up to get visible normal perturbation)
                scale = strength * 50.0
                nx = -sx * scale
                ny = -sy * scale
                nz = np.ones_like(nx)

                length = np.sqrt(nx*nx + ny*ny + nz*nz)
                length = np.maximum(length, 1e-6)
                nx /= length
                ny /= length
                nz /= length

                if base_normal_path_str:
                    base_normal_path = Path(base_normal_path_str)
                    if base_normal_path.exists():
                        base_img = Image.open(base_normal_path).convert("RGB")
                        # Resize heightmap-derived normals to match base
                        if (h_arr.shape[1], h_arr.shape[0]) != base_img.size:
                            # Recompute at base resolution
                            hmap_r = hmap.resize(base_img.size, Image.LANCZOS)
                            h_arr_r = np.array(hmap_r, dtype=np.float32) / 255.0
                            padded_r = np.pad(h_arr_r, 1, mode="wrap")
                            sx = (
                                -padded_r[:-2, :-2] + padded_r[:-2, 2:]
                                - 2.0 * padded_r[1:-1, :-2] + 2.0 * padded_r[1:-1, 2:]
                                - padded_r[2:, :-2] + padded_r[2:, 2:]
                            )
                            sy = (
                                -padded_r[:-2, :-2] - 2.0 * padded_r[:-2, 1:-1] - padded_r[:-2, 2:]
                                + padded_r[2:, :-2] + 2.0 * padded_r[2:, 1:-1] + padded_r[2:, 2:]
                            )
                            nx = -sx * scale
                            ny = -sy * scale
                            nz = np.ones_like(nx)
                            length = np.sqrt(nx*nx + ny*ny + nz*nz)
                            length = np.maximum(length, 1e-6)
                            nx /= length
                            ny /= length
                            nz /= length

                        # UDN blend with existing normal
                        base_arr = np.array(base_img, dtype=np.float32)
                        bx = base_arr[..., 0] / 127.5 - 1.0
                        by = base_arr[..., 1] / 127.5 - 1.0
                        bz = base_arr[..., 2] / 127.5 - 1.0

                        rx = bx + nx
                        ry = by + ny
                        rz = bz
                        length = np.sqrt(rx*rx + ry*ry + rz*rz)
                        length = np.maximum(length, 1e-6)
                        nx = rx / length
                        ny = ry / length
                        nz = rz / length

                # Encode to [0,255]
                out_arr = np.zeros((*nx.shape, 3), dtype=np.uint8)
                out_arr[..., 0] = np.clip((nx + 1.0) * 127.5, 0, 255).astype(np.uint8)
                out_arr[..., 1] = np.clip((ny + 1.0) * 127.5, 0, 255).astype(np.uint8)
                out_arr[..., 2] = np.clip((nz + 1.0) * 127.5, 0, 255).astype(np.uint8)
                Image.fromarray(out_arr).save(out_path, "PNG")
                generated.append(out_path)

        except Exception as exc:  # noqa: BLE001
            warnings.append(
                f"Texture processing failed for {op.output_filename}: {exc}"
            )
            continue

    return generated, warnings


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
    referenced_guids: set[str] | None = None,
) -> MaterialMapResult:
    """
    Parse .mat files in a Unity project, convert to Roblox material
    definitions, process textures, and generate UNCONVERTED.md.

    Args:
        unity_project_path: Root of the Unity project (contains Assets/).
        output_dir: Where to write generated textures and UNCONVERTED.md.
        referenced_guids: If provided, only process .mat files whose GUID
            appears in this set (as discovered from scene/prefab
            MeshRenderer components).  When None, process all .mat files.

    Returns:
        MaterialMapResult with all conversion results and aggregate stats.
    """
    unity_path = Path(unity_project_path).resolve()
    out_dir = Path(output_dir).resolve()
    textures_dir = out_dir / "textures"

    # 1. Build GUID map
    guid_map = _build_guid_map(unity_path)

    # Build reverse map (asset_path → guid) for filtering by referenced_guids
    path_to_guid: dict[Path, str] | None = None
    if referenced_guids is not None:
        path_to_guid = {path: guid for guid, path in guid_map.items()}

    # 2–4. Parse and convert each .mat file
    assets_dir = unity_path / "Assets"
    results: list[MaterialConversionResult] = []
    all_tex_ops: list[TextureOperation] = []

    if assets_dir.is_dir():
        for mat_path in sorted(assets_dir.rglob("*.mat")):
            # Skip materials not referenced by any scene or prefab
            if path_to_guid is not None:
                mat_guid = path_to_guid.get(mat_path, "")
                if mat_guid not in referenced_guids:
                    continue
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
    generated, tex_warnings = _process_textures(all_tex_ops, textures_dir)

    # 6. Generate UNCONVERTED.md
    unconverted_path = out_dir / config.UNCONVERTED_FILENAME
    _generate_unconverted_md(results, unity_path.name, unconverted_path)

    # Build result — keyed by material file path (unique) rather than name
    roblox_defs: dict[Path, RobloxMaterialDef] = {}
    companion_scripts: dict[Path, list[str]] = {}
    for r in results:
        if r.roblox_def:
            roblox_defs[r.material_path] = r.roblox_def
        if r.companion_scripts:
            companion_scripts[r.material_path] = r.companion_scripts

    total = len(results)
    fully = sum(1 for r in results if r.fully_converted)
    partial = sum(1 for r in results if not r.fully_converted and r.roblox_def is not None)
    unconvertible = sum(1 for r in results if r.roblox_def is None)

    return MaterialMapResult(
        materials=results,
        roblox_defs=roblox_defs,
        companion_scripts=companion_scripts,
        generated_textures=generated,
        unconverted_md_path=unconverted_path,
        total=total,
        fully_converted=fully,
        warnings=tex_warnings,
        partially_converted=partial,
        unconvertible=unconvertible,
        texture_ops_performed=len(generated),
    )
