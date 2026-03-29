# Unsupported Conversions & Known Limitations

> Last updated: 2026-03-29
> Status: Living document — shrinks as converter improves

This document catalogs everything the Unity-to-Roblox converter **cannot currently handle**,
categorized by severity and with workaround guidance. It covers both Roblox platform
limitations (permanent) and converter gaps (fixable in future releases).

---

## Quick Reference: What Works vs What Doesn't

### Fully Supported (Automated)

| Feature | Confidence | Notes |
|---------|------------|-------|
| Albedo texture (`_MainTex` / `_BaseMap`) | High | Direct copy to `SurfaceAppearance.ColorMap` |
| Color tint (`_Color` / `_BaseColor`) | High | Maps to `SurfaceAppearance.Color` |
| Normal maps (`_BumpMap`) | High | Direct copy (OpenGL format) |
| Metallic maps (R channel extraction) | High | From `_MetallicGlossMap` R channel |
| Roughness (smoothness inversion) | High | From `_MetallicGlossMap` A channel, inverted |
| Emission maps + color | High | Grayscale mask + tint + strength |
| Render mode (opaque/cutout/transparent) | High | `_Mode` → `AlphaMode` mapping |
| Occlusion maps | Medium | Baked into ColorMap via multiply |
| Flat color materials (no textures) | High | `BasePart.Color3` fallback |
| Scene hierarchy (parent/child) | High | Preserved in .rbxl output |
| Transform position | High | Direct mapping (Y-up in both) |
| Transform scale → Part size | High | `m_LocalScale` multiplied into part size |
| Rotation (quaternion → CFrame) | High | Full rotation matrix via `_quat_to_rotation_matrix()` |
| Material Color3/Transparency on plain Parts | High | Applied via `BasePart.Color3` and `BasePart.Transparency` |
| Point / Spot lights | High | Converted to `PointLight` / `SpotLight` children |
| Audio sources | High | Converted to `Sound` children with volume, pitch, loop |
| Particle systems | High | Converted to `ParticleEmitter` with rate, lifetime, speed, color |
| Prefab instantiation in scenes | High | Resolved from `PrefabLibrary`, inserted into scene tree |
| Prefab property modifications | High | `m_Modifications` applied to resolved prefab nodes |
| C# → Luau transpilation (AI) | Medium | Requires Claude API key |
| .rbxl XML generation | High | Valid Roblox Studio format |
| Roblox Open Cloud upload | High | Place + texture upload |
| Mesh decimation (>10K faces) | High | Conservative reduction via trimesh |
| GUID resolution | High | Bidirectional index from .meta files |
| UNCONVERTED.md generation | High | Per-conversion transparency report |
| Built-in Standard shader | High | Full property mapping |
| Standard (Specular) → Metallic | Medium | Luminance-based specular-to-metallic conversion |
| URP Lit/Unlit shaders | High | Property name normalization |
| URP alpha handling (`_Surface`+`_AlphaClip`) | High | Full mapping to AlphaMode |
| HDRP Lit shader (MaskMap MODS) | Medium | R=Metal, G=AO, A=Smooth extraction |
| Legacy Diffuse shader | High | `_Color` + `_MainTex` |
| Legacy Bumped/Specular shaders | Medium | Normal maps + specular-to-metallic |
| Normal map scale baking | High | `_BumpScale` baked into normal map pixels |
| Smoothness from albedo alpha | High | `_SmoothnessTextureChannel=1` support |
| Texture offset (pixel shift) | High | UV offset applied via pixel shifting |
| Custom shader identification | Medium | Source parsing + `#include` resolution |
| Ghost property detection | High | Only converts properties the shader actually reads |
| Detail albedo compositing | High | Overlay blend into ColorMap with tiling + mask |
| Detail normal blending | High | UDN blend into NormalMap with tiling + mask + scale |
| Height map → normal detail | High | Sobel filter conversion with optional base blend |
| Vertex color baking | Medium | Rasterise vertex colors to UV texture, multiply into albedo |
| UI Canvas → ScreenGui | High | Canvas/Text/Image/Button → ScreenGui/TextLabel/ImageLabel/TextButton |
| Companion Luau scripts | Medium | Generated for blink/rotation effects |
| Directional Light → Lighting | High | Maps to Roblox `Lighting` service properties |
| Unity primitives → Roblox shapes | Medium | Cube→Block, Sphere→Ball, Cylinder→Cylinder |
| Camera → Workspace.CurrentCamera | High | FOV, CFrame, near/far clip |
| Unlit game detection | Medium | Auto-adjusts Lighting when >70% unlit shaders |
| Skybox material → Sky object | Medium | 6-sided skybox textures in Lighting |
| Mesh bounding box → Part size | Medium | trimesh AABB used as base size for MeshParts |
| Collider → Part sizing | High | Box, Sphere, Capsule colliders set part size |
| Rigidbody kinematic detection | High | `m_IsKinematic` → `Anchored` property |

### NOT Supported (Detailed Below)

| Feature | Severity | Fixable? | Section |
|---------|----------|----------|---------|
| Vertex colors | **HIGH** | Partial | [Vertex Colors](#vertex-colors) |
| Multi-material meshes | **HIGH** | Future | [Multi-Material Meshes](#multi-material-meshes) |
| UV tiling ≠ (1,1) | **HIGH** | Partial | [UV Tiling](#uv-tiling-and-offset) |
| Terrain / splat maps | **HIGH** | Future | [Terrain](#terrain-conversion) |
| Custom Shader Graph | MEDIUM | Partial | [Shader Graph](#custom-shader-graph) |
| SSS / anisotropy / iridescence | LOW | No | [HDRP Advanced](#hdrp-advanced-features) |

---

## Remaining Gaps

### Material & Shader Gaps

#### Vertex Colors — PARTIALLY FIXED

**Severity**: HIGH → MEDIUM (automated baking now available for supported formats)

**Impact**: Any material that multiplies `_MainTex` by vertex colors loses per-vertex
color variation. This affects 43 of 72 materials in Trash Dash.

**Why**: Roblox `MeshPart` + `SurfaceAppearance` does not read vertex colors from mesh
data. There is no property to enable vertex color multiplication.

**What's now automated** (`modules/vertex_color_baker.py`):
- Loads mesh via trimesh (supports OBJ, PLY, GLB/GLTF formats)
- Extracts per-vertex RGBA colors and UV coordinates
- Rasterises vertex colors onto UV-space texture via barycentric interpolation
- Multiplies rasterised color map into albedo texture
- Batch processing API for all meshes in a project

**FBX dominant-color fallback** (`conversion_helpers.py:extract_fbx_dominant_color()`):
For FBX meshes that have vertex colors but no associated texture, the pipeline extracts
the average vertex color directly from the FBX binary (`LayerElementColor` section) and
sets `BasePart.Color3` to that color. This is a flat-color approximation (one color
instead of per-vertex variation), but it's dramatically better than default gray for
environment meshes like roads, buildings, sky backdrops, and street furniture.

**Remaining limitation**: Full per-vertex color baking (trimesh rasterization) does not
support FBX format natively. FBX meshes get the dominant-color fallback; OBJ/PLY/GLB
meshes get full UV-mapped vertex color baking via `vertex_color_baker.py`.

#### Multi-Material Meshes

**Severity**: HIGH
**Why**: Roblox allows only **one material per MeshPart**. Unity meshes can have
multiple sub-meshes, each with its own material slot.

**Current behavior**: The converter uses the first material reference from
`MeshRenderer.m_Materials[]` and ignores the rest.

**Workaround** (manual): Split the mesh into multiple MeshParts in Blender, one per
material slot.

**Future automation**: Parse FBX sub-meshes, split geometry at material boundaries,
create separate MeshParts.

#### UV Tiling and Offset

**Severity**: HIGH (when tiling ≠ 1,1)
**Why**: `SurfaceAppearance` has **no tiling or offset properties**. Textures map 1:1
to UV0.

**Current behavior**: Tiling values are read but not acted on. If `_MainTex_ST.xy ≠ (1,1)`,
the texture will appear un-tiled.

**Workaround strategies**:

| Tiling Factor | Strategy | Quality |
|--------------|----------|---------|
| (1, 1) | No action needed | Perfect |
| ≤ (4, 4) | Pre-tile the texture image | Good (loses resolution per tile) |
| > (4, 4) | Modify mesh UVs in the FBX | Best (requires mesh editing) |

**Implementation**: The `material_mapper.py` generates `pre_tile` texture operations
and `_process_textures()` now fully executes them, including offset pixel shifting.
Tiling factors ≤ 4x are pre-tiled automatically; factors > 4x are logged to UNCONVERTED.md.

#### Custom Shader Graph

**Severity**: MEDIUM (variable per game)
**Status**: Best-effort property extraction

Custom Shader Graph shaders (.shadergraph) are not parsed. The converter can only
identify custom `.shader` files by parsing their source code for property references
and `#include` resolution.

For Shader Graph materials, the converter falls back to checking if standard property
names (`_BaseMap`, `_Color`) exist in the material's saved properties.

---

## Script Transpilation Gaps

### C# to Luau Transpilation Quality

**Severity**: NEGLIGIBLE
**Status**: All transpilation uses Claude AI (requires Claude API key)

The transpiler sends each C# script to Claude along with the Unity Bridge API
reference and receives Roblox-native Luau in return. Claude handles architectural
adaptation, not just syntax translation:
- MonoBehaviour class → Luau module with lifecycle hooks
- Inspector-serialized fields → config table or attributes
- Inheritance / interfaces → restructured ModuleScript patterns
- LINQ expressions → idiomatic Luau equivalents
- Coroutines (`IEnumerator`, `yield return`) → `task.spawn` / `task.wait`
- Complex generics, event subscriptions, delegates → correctly rewritten
- 50+ Unity API → Roblox equivalents (informed by `api_mappings.py`)
- Script client/server/module classification based on API usage
- Automatic Roblox service imports based on detected API usage

**Post-transpilation validation**: `code_validator.py` checks generated Luau for
block keyword balance, residual C# syntax, curly braces, trailing semicolons, and
bracket balance. Scripts with validation errors are flagged for review.

---

## Roblox Platform Limitations (Permanent)

These are engine-level restrictions that **cannot be worked around** in the converter:

| Limitation | Impact | Status |
|------------|--------|--------|
| No custom shaders | Vertex shader effects (world curve, wave) cannot be replicated | Permanent |
| 1 material per MeshPart | Multi-material meshes must be split | Permanent |
| UV0 only | Secondary UV channels (lightmaps on UV1) are lost | Permanent |
| No height/displacement mapping | Parallax effects lost | Permanent |
| No SSS / anisotropy / iridescence / clear coat | HDRP advanced materials simplified | No plans |
| No per-material cubemap reflections | Legacy reflective shaders lose custom reflections | Engine uses probes |
| Max 4096x4096 texture | Textures larger than this are downscaled | Platform limit |
| SurfaceAppearance on MeshPart only | Primitive shapes (Part) can't use PBR textures | By design |
| No runtime SurfaceAppearance changes | Material property animation requires BasePart.Color workaround | PluginSecurity |
| No SurfaceAppearance tiling/offset | Repeating textures need pre-tiling or UV modification | Feature request open |
| 10,000 face limit per MeshPart | High-poly meshes need decimation | Platform limit |
| No vertex color reading | Vertex colors in mesh data are ignored by SurfaceAppearance | No plans |

### HDRP Advanced Features

These Unity HDRP material properties have **no Roblox equivalent**:

| Property | Description |
|----------|-------------|
| `_SubsurfaceMask` / `_SubsurfaceMaskMap` | Subsurface scattering |
| `_Thickness` / `_ThicknessMap` | Translucency |
| `_Anisotropy` / `_AnisotropyMap` | Anisotropic highlights |
| `_IridescenceThickness` / Map | Thin-film interference |
| `_CoatMask` / `_CoatMaskMap` | Clear coat layer |
| `_BentNormalMap` | Bent normals for indirect lighting |

---

## Terrain Conversion

**Severity**: HIGH
**Status**: Not implemented

Unity Terrain uses splat maps (`_Control`) with up to 4 texture layers (`_Splat0-3`)
and corresponding normal maps (`_Normal0-3`). Roblox has a `Terrain` object with
`MaterialVariant` for custom materials.

**Mapping strategy** (future):
1. Read the splat map (RGBA, each channel = one terrain layer's weight)
2. Create Roblox `MaterialVariant` objects for each layer
3. Programmatically paint Roblox terrain voxels based on splat map weights

This is a significant implementation effort and is tracked as a Phase 3 feature.

---

## Report Accuracy Notes

### Materials Processed Count

Materials are only processed if their GUID appears in a scene's or prefab's
`referenced_material_guids`. Materials that exist in the project but aren't referenced
by any scene renderer are silently skipped. The total count in the report reflects
only processed materials, not all `.mat` files found.

---

## Future Roadmap

1. Multi-material mesh splitting
2. Terrain splat map → MaterialVariant conversion
3. Custom Shader Graph analysis (.shadergraph parsing)

---

## Test Coverage

**Current**: 1003 automated tests across 33 test files covering:
- `test_unity_yaml_utils.py` — YAML parsing, vector/quaternion extraction, references
- `test_conversion_helpers.py` — All component conversion helpers (colliders, lights, audio, particles, materials)
- `test_converter.py` / `test_converter_detailed.py` / `test_converter_e2e.py` — End-to-end node-to-part, prefab resolution, scene conversion, report building
- `test_scene_parser.py` / `test_scene_parser_detailed.py` — Scene YAML parsing, hierarchy building
- `test_prefab_parser.py` / `test_prefab_parser_detailed.py` — Prefab YAML parsing
- `test_material_mapper.py` / `test_material_mapper_detailed.py` — Shader property mapping, pipeline detection
- `test_code_transpiler.py` / `test_code_transpiler_detailed.py` — C# → Luau AI transpilation
- `test_api_mappings.py` — API call/type/lifecycle mapping tables
- `test_llm_cache.py` — LLM response caching, TTL, eviction
- `test_retry.py` — Retry logic, backoff, exception handling
- `test_asset_extractor.py` — Asset file discovery
- `test_code_validator.py` — Luau syntax validation
- `test_guid_resolver.py` / `test_guid_resolver_detailed.py` — GUID index building
- `test_rbxl_writer.py` / `test_rbxl_writer_detailed.py` — .rbxl XML serialization
- `test_mesh_decimator.py` / `test_mesh_decimator_detailed.py` — Mesh decimation
- `test_animation_converter.py` — Animator controller/clip parsing, config generation
- `test_scriptable_object_converter.py` — ScriptableObject → Luau data tables
- `test_ui_translator.py` — Canvas → ScreenGui conversion
- `test_vertex_color_baker.py` — Vertex color baking to UV textures
- `test_roblox_uploader.py` — Upload, patching, MeshLoader injection
- `test_report_generator.py` — Report generation
- `test_package_generation.py` — .rbxm prefab package generation
- `test_generic_game_support.py` — Multi-game converter genericity

**Still needed**:
- Integration test: full pipeline on synthetic project, assert output structure
- Regression test: known-good .rbxl output comparison
