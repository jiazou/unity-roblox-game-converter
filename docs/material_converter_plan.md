# Material Converter — Implementation Plan

> Status: Implemented
> Author: Claude
> Date: 2026-03-01
> Depends on: `docs/material_mapping_research.md`, `docs/trash_dash_UNCONVERTED.md`

---

## Overview

Build `modules/material_mapper.py` — a new pipeline module that parses Unity `.mat` files,
resolves texture GUIDs, identifies active shader properties, and produces Roblox-ready
material definitions + an UNCONVERTED.md report of features it couldn't handle.

This module follows the existing architecture: no inter-module imports, one public function,
dataclass-based contracts, wired through `converter.py`.

---

## Architecture

```
converter.py (orchestrator)
    │
    │  ── Phase 1: Discovery (lightweight YAML reads) ──
    │
    ├── scene_parser.parse_scene()           ← already exists; moved BEFORE materials
    │       returns ParsedScene[] with referenced_material_guids
    │
    ├── prefab_parser.parse_prefabs()        ← already exists; moved BEFORE materials
    │       returns PrefabLibrary
    │
    │  ── Phase 2: Asset inventory ──
    │
    ├── asset_extractor.extract_assets()     ← already exists
    │       returns AssetManifest (with .meta files tracked)
    │
    │  ── Phase 3: Heavy processing (informed by Phase 1) ──
    │
    ├── material_mapper.map_materials()      ← NEW
    │       inputs:  unity_project_path, output_dir
    │       optional: referenced_guids from scene/prefab parsing
    │       returns: MaterialMapResult
    │         ├── per-material conversion results
    │         ├── list of generated textures (extracted channels, resized, etc.)
    │         └── UNCONVERTED.md content
    │
    ├── code_transpiler                      ← already exists (parallel with materials)
    │
    │  ── Phase 4: Assembly ──
    │
    ├── rbxl_writer.write_rbxl()             ← MODIFIED to accept material data
    │       now takes MaterialMapResult to attach SurfaceAppearance to parts
    │
    └── report_generator                     ← MODIFIED to include material stats
            now writes UNCONVERTED.md alongside JSON report
```

### Pipeline Ordering Rationale

The pipeline runs **scenes and prefabs first** because they are cheap (YAML parsing
only) and they reveal which materials are actually referenced by the project's
MeshRenderer components. This information feeds forward into material mapping, which
can then:

1. **Skip orphaned `.mat` files** whose GUIDs never appear in any scene or prefab
2. **Resolve scene→material→texture attachment** for the RBXL writer (MeshRenderer
   `m_Materials[].guid` → material name → `RobloxMaterialDef`)

Material mapping and code transpilation are independent of each other and could run
in parallel. Both must complete before RBXL writing (the join point).

**Concrete changes for reordering:**

| File | Change |
|------|--------|
| `converter.py` | Move scene/prefab parsing stages before material mapping |
| `scene_parser.py` | Extract material GUIDs from `MeshRenderer.m_Materials` → expose `referenced_material_guids: set[str]` on `ParsedScene` |
| `material_mapper.map_materials()` | Accept optional `referenced_guids: set[str] \| None`; when provided, skip `.mat` files not in the set; when `None`, process all (standalone mode) |
| `converter.py _scene_nodes_to_parts()` | Wire `mat_result.roblox_defs` into `RbxPartEntry.surface_appearance` by resolving each node's material GUID |

---

## Implementation Steps

### Step 1: GUID Resolver

**File**: `modules/material_mapper.py` (new)

Build a GUID → file path lookup table by scanning all `.meta` files in the project.

```python
def _build_guid_map(unity_project_path: Path) -> dict[str, Path]:
    """Scan all .meta files, extract guid field, return {guid: asset_path}."""
```

Unity `.meta` files are small YAML files like:
```yaml
fileFormatVersion: 2
guid: 6d0752c619fa62b45...
```

The asset path is the `.meta` file's path minus the `.meta` suffix.

**Depends on**: PyYAML (already a dependency)
**Estimated size**: ~20 lines

### Step 2: Shader Identifier

Identify which shader a material uses by resolving `m_Shader` references.

```python
@dataclass
class ShaderInfo:
    name: str           # e.g. "Unlit/CurvedUnlit", "Standard", "URP/Lit"
    category: str       # "standard" | "urp_lit" | "urp_unlit" | "legacy" | "particle" | "custom_unlit" | "custom_unlit_alpha" | "vertex_color" | "unknown"
    is_transparent: bool
    uses_vertex_colors: bool
    reads_color: bool   # whether shader actually reads _Color/_BaseColor
    reads_maintex: bool
    source_path: Path | None  # path to .shader file if custom

def _identify_shader(
    shader_ref: dict,
    guid_map: dict[str, Path],
    unity_project_path: Path,
) -> ShaderInfo:
```

**Logic**:
1. If `fileID` is a known built-in (46=Standard, 10720=Legacy/Diffuse, 10751=Particles/AlphaBlended, 10752=Particles/Premultiply, 10753=Particles/Additive, 200=Sprites/Default), return immediately with known properties.
2. If `fileID == 4800000` (MonoScript reference), resolve `guid` via guid_map to find the `.shader` file.
3. Parse the `.shader` file **and resolve local `#include` files** (.cginc/.hlsl in the same directory) to build a combined source. Then extract:
   - Shader name (first line: `Shader "Name/Path"`)
   - `Tags { "RenderType" = "Transparent" }` → transparency
   - `Blend` directives → transparency
   - `ZWrite Off` → transparency hint
   - Whether `i.color` / `v.color` is used → vertex colors (searched in full source + includes)
   - Whether `_Color`/`_BaseColor` or `_MainTex`/`_BaseMap` appear **anywhere** in the combined source → `reads_color`, `reads_maintex`
4. **Property detection rationale**: The `Properties {}` block only declares what the Inspector exposes — it does NOT reliably indicate what compiled passes actually sample. A property can be set via script without appearing in Properties, and a declared property may go entirely unused in the shader code. Therefore we search the full source (including resolved includes) for property name references, not just the Properties block.
5. **Conservative fallbacks**: If the shader source is unreadable (OSError), too short (<200 chars, e.g. UsePass/Fallback only), or completely unresolvable (unknown GUID), default to `reads_color=True, reads_maintex=True`. It is better to include a ghost property than to silently drop a real one.
6. For URP package shaders (GUID not found in Assets/), fall back to known URP property conventions (check for `_BaseMap` in material properties).

**Estimated size**: ~80 lines

### Step 3: Material Property Extractor

Parse `.mat` YAML files and extract properties that the shader is known to use.

```python
@dataclass
class ParsedMaterial:
    name: str
    path: Path
    shader: ShaderInfo
    # Normalized properties (only set if shader reads them)
    albedo_tex_guid: str | None       # _MainTex / _BaseMap GUID
    albedo_tex_path: Path | None      # resolved file path
    albedo_tex_tiling: tuple[float, float]   # (sx, sy)
    albedo_tex_offset: tuple[float, float]   # (ox, oy)
    albedo_color: tuple[float, float, float, float] | None  # _Color / _BaseColor RGBA
    normal_tex_path: Path | None
    normal_scale: float
    metallic_tex_path: Path | None    # _MetallicGlossMap / _MaskMap
    metallic_value: float             # scalar fallback
    smoothness_value: float           # scalar fallback
    smoothness_source: int            # 0=metallic alpha, 1=albedo alpha
    ao_tex_path: Path | None
    ao_strength: float
    emission_tex_path: Path | None
    emission_color: tuple[float, float, float]
    render_mode: int                  # 0=opaque, 1=cutout, 2=fade, 3=transparent
    alpha_cutoff: float
    tint_color: tuple[float, float, float, float] | None  # _TintColor (particles)
    # Custom shader specific
    custom_properties: dict[str, Any]  # e.g. _CurveStrength, _BlinkingValue
```

The parser must handle BOTH `.mat` YAML formats:
- Serialized version 3 (newer): `- _MainTex: {m_Texture: ...}`
- Serialized version 2 (older): `- first: {name: _MainTex} second: {m_Texture: ...}`

```python
def _parse_material(
    mat_path: Path,
    guid_map: dict[str, Path],
    shader_info: ShaderInfo,
) -> ParsedMaterial:
```

**Key correctness rule**: Only populate properties that `shader_info` says the shader reads.
For example, if `shader_info.reads_color == False` (i.e. neither `_Color` nor `_BaseColor`
appear anywhere in the shader source or its includes), leave `albedo_color = None` even if
the `.mat` file stores a non-white `_Color` — that value is a "ghost property" that the
shader never samples.  When in doubt (unreadable shader, short source), `reads_color`
defaults to `True` so real properties are never silently dropped.

**Estimated size**: ~120 lines

### Step 4: Material Converter Core

Convert a `ParsedMaterial` into a Roblox material definition.

```python
@dataclass
class TextureOperation:
    """A texture processing operation to be executed."""
    operation: str          # "copy" | "extract_channel" | "invert" | "resize" | "bake_ao" | "threshold_alpha" | "pre_tile" | "to_grayscale"
    source_path: Path
    output_filename: str
    channel: str | None     # "R", "G", "B", "A" for extract_channel
    params: dict[str, Any]  # operation-specific parameters

@dataclass
class RobloxMaterialDef:
    """Roblox material definition ready for rbxl_writer."""
    # Maps to SurfaceAppearance properties
    color_map: str | None           # output texture filename
    normal_map: str | None
    metalness_map: str | None
    roughness_map: str | None
    emissive_mask: str | None
    emissive_strength: float
    emissive_tint: tuple[float, float, float]
    color_tint: tuple[float, float, float]  # SurfaceAppearance.Color
    alpha_mode: str                 # "Opaque" | "Transparency" | "Overlay"
    # Falls back to BasePart properties when no SurfaceAppearance needed
    base_part_color: tuple[float, float, float] | None
    base_part_transparency: float
    base_part_material: str         # "SmoothPlastic", "Neon", etc.

@dataclass
class UnconvertedFeature:
    feature_name: str
    unity_property: str
    severity: str               # "LOW" | "MEDIUM" | "HIGH"
    workaround: str
    auto_fixable_future: bool

@dataclass
class MaterialConversionResult:
    material_name: str
    material_path: Path
    shader_name: str
    roblox_def: RobloxMaterialDef | None  # None if fully unconvertible
    texture_ops: list[TextureOperation]
    unconverted: list[UnconvertedFeature]
    warnings: list[str]
    companion_scripts: list[str]    # Luau scripts to generate (e.g. blink, rotate)
    fully_converted: bool

def _convert_material(parsed: ParsedMaterial) -> MaterialConversionResult:
```

**Conversion logic** (follows the decision flowchart from research doc):

1. **No shader / unknown shader** → log all properties as unconverted, return `None` def
2. **Standard / URP Lit / Legacy Diffuse**:
   - `_MainTex` → `color_map` (TextureOp: "copy" or "resize")
   - `_Color` (if non-white and shader reads it) → `color_tint`
   - `_MetallicGlossMap` → extract R → `metalness_map`, extract A + invert → `roughness_map`
   - `_BumpMap` → `normal_map` (copy, warn if `_BumpScale ≠ 1`)
   - `_OcclusionMap` → bake into `color_map` (TextureOp: "bake_ao")
   - `_EmissionMap` → grayscale → `emissive_mask`, color → `emissive_tint`
   - `_Mode` → `alpha_mode`
3. **URP Unlit / Custom Unlit (CurvedUnlit family)**:
   - `_MainTex` → `color_map`
   - Skip `_Color` (shader doesn't read it)
   - Log vertex colors, world curve as unconverted
   - For CurvedUnlitAlpha: set `alpha_mode = "Transparency"`
4. **UnlitBlinking** → `color_map` + companion blink script
5. **CurvedRotation** → `color_map` + companion rotation script
6. **VertexColor** → fully unconverted, log for manual work
7. **Particle shaders** → `color_map` + `tint_color`, log blend mode

**Estimated size**: ~150 lines

### Step 5: Texture Processor

Execute `TextureOperation` objects to produce output textures.

```python
def _process_textures(
    ops: list[TextureOperation],
    source_root: Path,
    output_dir: Path,
) -> list[Path]:
```

Operations:
- **copy**: Copy file, resize if exceeds `config.TEXTURE_MAX_RESOLUTION` (default 4096)
- **extract_channel**: Load image, extract R/G/B/A channel, save as grayscale PNG
- **invert**: `255 - pixel` (smoothness → roughness)
- **bake_ao**: `albedo_pixel * lerp(1, ao_pixel, strength)`
- **threshold_alpha**: Binary alpha at cutoff value
- **pre_tile**: Tile NxM and downscale to `config.TEXTURE_MAX_RESOLUTION`
- **to_grayscale**: Luminance conversion for emission

**Dependency**: Pillow (PIL) — needs to be added to `requirements.txt`

**Estimated size**: ~80 lines

### Step 6: UNCONVERTED.md Generator

Generate the Smartdown file from aggregated `MaterialConversionResult` objects.

```python
def _generate_unconverted_md(
    results: list[MaterialConversionResult],
    project_name: str,
    output_path: Path,
) -> Path:
```

Follows the template structure from `docs/smartdown_template.md`.

**Estimated size**: ~100 lines

### Step 7: Public API (Top-Level Function)

```python
@dataclass
class MaterialMapResult:
    """Top-level output of the material mapping pipeline."""
    materials: list[MaterialConversionResult]
    roblox_defs: dict[str, RobloxMaterialDef]  # material_name → def
    generated_textures: list[Path]
    unconverted_md_path: Path | None
    # Aggregate stats
    total: int
    fully_converted: int
    partially_converted: int
    unconvertible: int
    texture_ops_performed: int

def map_materials(
    unity_project_path: str | Path,
    asset_manifest: "asset_extractor.AssetManifest",
    output_dir: str | Path,
) -> MaterialMapResult:
    """
    Parse all .mat files, resolve shaders, convert to Roblox material
    definitions, process textures, and generate UNCONVERTED.md.
    """
```

This is the single entry point called by `converter.py`.

**Estimated size**: ~50 lines

### Step 8: Integration with converter.py

Modify the orchestrator to wire material_mapper into the pipeline **after**
scene/prefab parsing (see Architecture section for rationale).

```python
# In converter.py — new stage order:
#   1. Scene parsing       (lightweight, discovers referenced material GUIDs)
#   2. Prefab parsing      (lightweight)
#   3. Asset extraction    (file inventory)
#   4. Material mapping    (heavy processing, can filter by referenced GUIDs)
#   5. Code transpilation  (independent)
#   6. RBXL writing        (join point)
#   7. Report generation

# Collect material GUIDs referenced by scenes
referenced_guids: set[str] = set()
for ps in parsed_scenes:
    referenced_guids |= ps.referenced_material_guids

click.echo("🎨  Mapping materials …")
try:
    mat_result = material_mapper.map_materials(
        unity_path, out_dir,
        referenced_guids=referenced_guids or None,  # None = process all
    )
    ...
```

Also modify `_scene_nodes_to_parts()` to attach material data to parts by resolving
each `MeshRenderer`'s `m_Materials[].guid` → material name → `mat_result.roblox_defs`
→ `RbxPartEntry.surface_appearance`.

### Step 9: Integration with rbxl_writer.py

Extend `RbxPartEntry` with material fields:

```python
@dataclass
class RbxPartEntry:
    name: str
    position: tuple[float, float, float] = (0.0, 4.0, 0.0)
    size: tuple[float, float, float] = (4.0, 1.0, 2.0)
    brick_color: str = "Medium stone grey"
    anchored: bool = True
    children: list["RbxPartEntry"] = field(default_factory=list)
    scripts: list[RbxScriptEntry] = field(default_factory=list)
    # NEW material fields
    color3: tuple[float, float, float] | None = None
    transparency: float = 0.0
    material_enum: str | None = None  # e.g. "SmoothPlastic"
    surface_appearance: "RbxSurfaceAppearance | None" = None

@dataclass
class RbxSurfaceAppearance:
    color_map: str | None = None         # asset path / placeholder
    normal_map: str | None = None
    metalness_map: str | None = None
    roughness_map: str | None = None
    emissive_mask: str | None = None
    emissive_strength: float = 1.0
    emissive_tint: tuple[float, float, float] = (1.0, 1.0, 1.0)
    color_tint: tuple[float, float, float] = (1.0, 1.0, 1.0)
    alpha_mode: str = "Opaque"
```

Modify `_make_part()` to emit SurfaceAppearance XML child items when `surface_appearance`
is set.

### Step 10: Integration with report_generator.py

Add a `MaterialSummary` dataclass and include it in `ConversionReport`:

```python
@dataclass
class MaterialSummary:
    total: int = 0
    fully_converted: int = 0
    partially_converted: int = 0
    unconvertible: int = 0
    textures_generated: int = 0
    unconverted_md_path: str = ""
```

### Step 11: Update config.py

Add material-specific configuration:

```python
# Material mapper options
TEXTURE_MAX_RESOLUTION: int = 4096          # Roblox allows up to 4096x4096
TEXTURE_OUTPUT_FORMAT: str = "png"
GENERATE_UNIFORM_TEXTURES: bool = True    # 4x4 PNGs for scalar values
PRE_TILE_MAX_FACTOR: int = 4              # max tiling before logging to UNCONVERTED
FLIP_NORMAL_GREEN_CHANNEL: bool = False   # set True for DirectX normal maps
```

### Step 12: Update requirements.txt

Add `Pillow` for texture processing:

```
Pillow>=10.0.0
```

---

## File Change Summary

| File | Action | Size Est. |
|------|--------|-----------|
| `modules/material_mapper.py` | **CREATE** | ~600 lines |
| `modules/rbxl_writer.py` | MODIFY | +50 lines |
| `converter.py` | MODIFY | +30 lines |
| `modules/report_generator.py` | MODIFY | +20 lines |
| `config.py` | MODIFY | +10 lines |
| `requirements.txt` | MODIFY | +1 line |
| `modules/__init__.py` | MODIFY (import) | +1 line |

**Total new code**: ~600 lines in material_mapper.py
**Total modifications**: ~110 lines across 5 existing files

---

## Dependency Graph (Build Order)

```
Step 1  (GUID resolver)           ← standalone, no deps
Step 2  (Shader identifier)       ← depends on Step 1; resolves #include files
Step 3  (Material property parser)← depends on Steps 1, 2
Step 4  (Converter core)          ← depends on Step 3
Step 5  (Texture processor)       ← depends on Step 4 output; needs Pillow
Step 6  (UNCONVERTED.md gen)      ← depends on Step 4 output
Step 7  (Public API)              ← wraps Steps 1-6; accepts optional referenced_guids
Step 8  (converter.py wiring)     ← depends on Step 7; reorders pipeline stages
Step 9  (rbxl_writer extension)   ← depends on Step 4 dataclasses
Step 10 (report_generator ext)    ← depends on Step 7 output
Step 11 (config.py)               ← standalone, do first
Step 12 (requirements.txt)        ← standalone, do first
```

**Recommended implementation order**: 12 → 11 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 9 → 8 → 10

### Runtime Pipeline Order (in converter.py)

```
Phase 1 — Discovery:        scene_parser → prefab_parser
Phase 2 — Inventory:        asset_extractor
Phase 3 — Heavy processing: material_mapper (filtered by Phase 1 GUIDs)
                            code_transpiler (independent, could run in parallel)
Phase 4 — Assembly:         rbxl_writer (joins scenes + materials + scripts)
Phase 5 — Reporting:        report_generator
```

---

## Testing Strategy

### Unit Test: Trash Dash Materials

Use the Trash Dash project at `/home/user/trash-dash` as a real-world test fixture:

1. **GUID resolver**: Assert `93d8fc18fdc65dd4aa903210d93f3343` resolves to `Assets/Shaders/CurvedUnlit.shader`
2. **Shader identifier**: Assert CurvedUnlit is categorized as `custom_unlit`, `is_transparent=False`, `uses_vertex_colors=True`, `reads_color=False` (full-source search of CurvedUnlit.shader + CurvedCode.cginc finds no `_Color` reference)
3. **Material parser**: Assert `Dog.mat` has `albedo_color=None` (not `(0.4, 0.4, 0.4)`) because neither CurvedUnlit.shader nor its included CurvedCode.cginc reference `_Color` — it is a ghost property
4. **Converter**: Assert `Dog.mat` produces a `RobloxMaterialDef` with `color_map` set and `color_tint = (1,1,1)` (no tint)
5. **UNCONVERTED.md**: Assert vertex color and world curve are logged for CurvedUnlit materials

### Integration Test

Run the full pipeline on Trash Dash and verify:
- 72 materials processed
- 12 fully converted, 49 partially, 7 unconvertible (± some depending on categorization)
- UNCONVERTED.md generated with correct counts
- No crashes on any material

---

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| `.mat` YAML format variations (serializedVersion 2 vs 3) | Handle both in parser, tested against Trash Dash which has both |
| Missing shader files (URP package shaders) | Fall back to property-name heuristics (_BaseMap present → URP) |
| Texture processing failures (corrupt/missing files) | Skip with warning, don't crash pipeline |
| Large texture memory usage | Process one texture at a time, don't hold all in memory |
| Custom Shader Graph shaders (not in Trash Dash) | Best-effort: extract known property names, log unknowns |
