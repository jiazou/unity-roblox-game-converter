# Unsupported Conversions & Known Limitations

> Last updated: 2026-03-02
> Converter version: 0.1.0 (pre-release)
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
| Position from Transform | High | Direct mapping (Y-up in both) |
| C# → Luau transpilation (AI mode) | Medium | Requires Claude API key |
| .rbxl XML generation | High | Valid Roblox Studio format |
| Roblox Open Cloud upload | High | Place + texture upload |
| Mesh decimation (>10K faces) | High | Conservative reduction via trimesh |
| GUID resolution | High | Bidirectional index from .meta files |
| UNCONVERTED.md generation | High | Per-conversion transparency report |
| Built-in Standard shader | High | Full property mapping |
| URP Lit/Unlit shaders | High | Property name normalization |
| Legacy Diffuse shader | High | `_Color` + `_MainTex` |
| Custom shader identification | Medium | Source parsing + `#include` resolution |
| Ghost property detection | High | Only converts properties the shader actually reads |
| Companion Luau scripts | Medium | Generated for blink/rotation effects |

### NOT Supported (Detailed Below)

| Feature | Severity | Fixable? | Section |
|---------|----------|----------|---------|
| Transform scale → Part size | **CRITICAL** | Yes | [Transform Scale](#transform-scale-not-applied) |
| Material on non-MeshPart objects | **HIGH** | Yes | [Material on Plain Parts](#materials-not-applied-to-plain-parts) |
| Vertex colors | **HIGH** | Future | [Vertex Colors](#vertex-colors) |
| Multi-material meshes | **HIGH** | Future | [Multi-Material Meshes](#multi-material-meshes) |
| UV tiling ≠ (1,1) | **HIGH** | Partial | [UV Tiling](#uv-tiling-and-offset) |
| Terrain / splat maps | **HIGH** | Future | [Terrain](#terrain-conversion) |
| Light / Camera objects | **MEDIUM** | Yes | [Non-Geometry Objects](#lights-cameras-and-non-geometry-objects) |
| C# transpilation (rule-based) | **MEDIUM** | Yes | [Script Transpilation](#c-to-luau-transpilation-quality) |
| Height/parallax maps | MEDIUM | Future | [Height Maps](#heightparallax-maps) |
| Detail maps | MEDIUM | Future | [Detail Maps](#detail-maps) |
| Custom Shader Graph | MEDIUM | Partial | [Shader Graph](#custom-shader-graph) |
| Part size from mesh bounds | MEDIUM | Yes | [Part Sizing](#part-sizing) |
| Particle systems | MEDIUM | Future | [Particles](#particle-systems) |
| Skybox generation | MEDIUM | Future | [Skybox](#skybox-and-atmosphere) |
| Rotation (quaternion → CFrame) | LOW | Yes | [Rotation](#rotation-mapping) |
| Unlit rendering | LOW | Partial | [Unlit Materials](#unlit-materials) |
| SSS / anisotropy / iridescence | LOW | No | [HDRP Advanced](#hdrp-advanced-features) |
| Normal map scale baking | LOW | Yes | [Normal Scale](#normal-map-scale) |
| Prefab instantiation in scenes | LOW | Yes | [Prefab Instances](#prefab-instances-in-scenes) |

---

## Critical Issues (Must Fix)

### Transform Scale Not Applied

**Severity**: CRITICAL
**Status**: Converter bug — all parts get hardcoded `(4.0, 1.0, 4.0)` size

Unity's `Transform.m_LocalScale` is parsed correctly from scene YAML but is not
used when creating `RbxPartEntry` objects. The `_node_to_part()` function in
`converter.py` sets a fixed default size instead of using the node's scale.

**Impact**: Every object in the converted scene has the wrong size. A `50x1x50`
ground plane appears as `4x1x4`.

**Fix**: Multiply the node's `m_LocalScale` into the part's `size` field.

### Materials Not Applied to Plain Parts

**Severity**: HIGH
**Status**: By design — `SurfaceAppearance` only attaches to `MeshPart`

When a GameObject has a `MeshRenderer` with material references but its mesh GUID
is a Unity built-in primitive (e.g., `0000000000000000e000000000000000` for Cube),
the GUID doesn't resolve to a file path. Without a `mesh_id`, the part is created
as a plain `Part` (not `MeshPart`), and `SurfaceAppearance` is skipped.

The material's `color3` and `transparency` should still be set on plain Parts via
`BasePart.Color3` and `BasePart.Transparency`, but currently this wiring only
triggers if the part is a MeshPart.

**Impact**: Objects using built-in Unity primitives (Cube, Sphere, Cylinder, Plane)
lose all material data. In the test run, Ground and Coin lost their materials.

**Fix**:
1. For non-MeshPart parts, apply `BasePart.Color3` from the material's `_Color`
2. Apply `BasePart.Transparency` from `_Mode` / `_Color.a`
3. Consider mapping Unity primitives to Roblox equivalents (Cube→Block, Sphere→Ball)

---

## Geometry & Transform Gaps

### Part Sizing

**Severity**: MEDIUM
**Status**: Not implemented

Parts are created with a fixed default size. The converter should derive size from
either the mesh's bounding box (for MeshParts) or the Transform scale (for primitive
shapes mapped to Roblox Parts).

### Rotation Mapping

**Severity**: LOW
**Status**: Not implemented

Unity `m_LocalRotation` (quaternion) is parsed but not converted to Roblox CFrame
rotation. All parts appear at identity rotation in the .rbxl output.

**Fix**: Convert `(x, y, z, w)` quaternion to CFrame rotation matrix.

### Prefab Instances in Scenes

**Severity**: LOW
**Status**: Prefabs are parsed but not instantiated

The converter parses `.prefab` files and tracks `PrefabInstance` references in scenes,
but does not actually insert prefab hierarchies into the scene tree at their
instantiation points.

**Fix**: When a scene references a prefab via `m_PrefabInstance`, resolve it from the
`PrefabLibrary` and insert its node subtree at the correct Transform position.

---

## Material & Shader Gaps

### Vertex Colors

**Severity**: HIGH
**Impact**: Any material that multiplies `_MainTex` by vertex colors (e.g., the entire
Trash Dash game — 43 of 72 materials) loses per-vertex color variation.

**Why**: Roblox `MeshPart` + `SurfaceAppearance` does not read vertex colors from mesh
data. There is no property to enable vertex color multiplication.

**Workaround** (manual): Bake vertex colors into the albedo texture using Blender or
Substance Painter.

**Future automation**: Parse FBX mesh → extract vertex colors at each UV coordinate →
multiply into albedo texture → export new texture. Requires FBX parsing library.

### Multi-Material Meshes

**Severity**: HIGH
**Why**: Roblox allows only **one material per MeshPart**. Unity meshes can have
multiple sub-meshes, each with its own material slot.

**Current behavior**: The converter uses the first material reference from
`MeshRenderer.m_Materials[]` and ignores the rest.

**Workaround** (manual): Split the mesh into multiple MeshParts in Blender, one per
material slot.

**Future automation**: Parse FBX sub-meshes, split geometry at material boundaries,
create separate MeshParts.

### UV Tiling and Offset

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

**Partial implementation**: The `material_mapper.py` generates `pre_tile` texture
operations, but the texture processor is not yet wired to execute them.

### Height/Parallax Maps

**Severity**: MEDIUM
**Why**: Roblox has no displacement or parallax mapping.

**Properties affected**: `_ParallaxMap`, `_HeightMap`, `_Parallax`, `_HeightAmplitude`

**Workaround**: Convert height map to additional normal map detail (Sobel filter).
Or drop entirely — visual impact is often subtle.

### Detail Maps

**Severity**: MEDIUM
**Why**: Roblox has no secondary texture layer system.

**Properties affected**: `_DetailAlbedoMap`, `_DetailNormalMap`, `_DetailMask`, `_UVSec`

**Workaround** (future): Composite detail albedo into main albedo respecting the
detail mask and different tiling rates. Blend detail normal into main normal.

### Custom Shader Graph

**Severity**: MEDIUM (variable per game)
**Status**: Best-effort property extraction

Custom Shader Graph shaders (.shadergraph) are not parsed. The converter can only
identify custom `.shader` files by parsing their source code for property references
and `#include` resolution.

For Shader Graph materials, the converter falls back to checking if standard property
names (`_BaseMap`, `_Color`) exist in the material's saved properties.

### Normal Map Scale

**Severity**: LOW
**Status**: Not implemented

When `_BumpScale ≠ 1.0`, the normal map intensity should be adjusted by scaling XY
channels and renormalizing Z. Currently the converter copies normal maps without
modification.

### Unlit Materials

**Severity**: LOW
**Impact**: Games designed as unlit (pre-baked lighting in textures) will receive
Roblox's realtime lighting on top, causing double-lighting.

**Why**: Roblox has no "unlit" `SurfaceAppearance` mode. `BasePart.Material = Neon`
is self-lit but has a strong glow effect.

**Workaround**: Set Roblox `Lighting.Ambient` high and `Lighting.Brightness` low to
approximate an unlit environment.

**Future**: Auto-detect unlit game (all materials use unlit shaders) and generate
appropriate Lighting configuration in the .rbxl.

---

## Script Transpilation Gaps

### C# to Luau Transpilation Quality

**Severity**: MEDIUM (rule-based mode) / LOW (AI mode)
**Status**: Rule-based transpiler is extremely simplistic

**What rule-based mode does**:
- Variable declarations: `int x = 5` → `local x = 5`
- Debug.Log → print
- `void Foo()` → `local function Foo()`
- Unity lifecycle stubs: `Start()` → `AncestryChanged`, `Update()` → `Heartbeat`
- `this.` → `self.`

**What rule-based mode does NOT handle**:
- C# class/namespace declarations (left as-is, produces invalid Luau)
- Braces `{ }` (left as-is)
- Type system (`int`, `float`, `bool`, `string`, generic types)
- Method calls (`.GetComponent<T>()`, `.AddForce()`, etc.)
- Loops (`for`, `foreach`, `while`)
- Conditional operators (`? :`, `??`)
- Properties (getters/setters)
- Inheritance / interfaces
- LINQ
- Coroutines (`IEnumerator`, `yield return`)
- Unity-specific APIs (Input, Physics, Collision, UI, NavMesh, etc.)
- Access modifiers (`public`, `private`, `protected`)
- `using` statements

**Result**: Rule-based output is essentially **invalid Luau with C# syntax artifacts**.
Scripts are flagged for review but the confidence scoring is unreliable.

**AI mode** (requires Claude API key): Produces much better results but requires
network access and API credits.

**Recommendation**: Always use `--use-ai` for production conversions. Rule-based mode
is only useful as a rough starting point for manual cleanup.

---

## Scene & Object Type Gaps

### Lights, Cameras, and Non-Geometry Objects

**Severity**: MEDIUM
**Status**: All GameObjects become Parts, regardless of type

The converter creates a Roblox Part for every GameObject in the scene, including
objects that should be mapped to non-Part Roblox instances:

| Unity Object | Should Map To | Current Behavior |
|-------------|---------------|-----------------|
| Directional Light | Roblox `Lighting` properties | Becomes a Part at light's position |
| Point Light | `PointLight` under nearest Part | Becomes a Part |
| Spot Light | `SpotLight` under nearest Part | Becomes a Part |
| Camera | `Workspace.CurrentCamera` setup | Becomes a Part |
| Canvas / UI | `ScreenGui` / `SurfaceGui` | Not handled |
| Audio Source | `Sound` under Part | Not handled |
| Particle System | `ParticleEmitter` | Not handled |
| Collider (no renderer) | Part with `Transparency=1` | Becomes visible Part |
| Empty GameObject | `Folder` or skip | Becomes a Part |

**Fix**: Check component types during `_node_to_part()` and map to appropriate Roblox
instances instead of always creating Parts.

### Particle Systems

**Severity**: MEDIUM
**Status**: Not converted

Unity `ParticleSystem` components are not parsed or converted to Roblox
`ParticleEmitter` objects. Particle materials (Additive, Alpha Blended, Premultiplied)
are partially handled in the material mapper but the emitter properties (rate, lifetime,
velocity, shape, color-over-lifetime) are not extracted.

### Skybox and Atmosphere

**Severity**: MEDIUM
**Status**: Not converted

Unity Skybox materials (6-sided, Procedural, Panoramic) are not mapped to Roblox
`Skybox` and `Atmosphere` objects.

**Future**: Detect skybox material type and generate appropriate Roblox Skybox
configuration in the .rbxl output.

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

## Report Accuracy Issues

### Parts Written Count

The conversion report's `parts_written` field counts only root-level parts passed to
`write_rbxl()`, not their children. If a scene has 1 root with 5 children, the report
says "1 part" but the .rbxl contains 6.

### Materials Processed Count

Materials are only processed if their GUID appears in a scene's or prefab's
`referenced_material_guids`. Materials that exist in the project but aren't referenced
by any scene renderer are silently skipped. The total count in the report reflects
only processed materials, not all `.mat` files found.

---

## Future Roadmap

### Phase 1 — Next Release (Converter Bugs)
1. Apply Transform scale to Part size
2. Apply material Color3/Transparency to plain Parts (not just MeshParts)
3. Map Unity primitives (Cube/Sphere/Cylinder/Plane) to Roblox equivalents
4. Convert rotation quaternion to CFrame
5. Skip or correctly map Light/Camera GameObjects
6. Instantiate prefabs in scene tree
7. Fix parts_written counting

### Phase 2 — Near Term (Feature Gaps)
8. UV pre-tiling texture processor
9. Normal map scale baking
10. Unlit game detection + Lighting configuration
11. Particle material → ParticleEmitter property mapping
12. Skybox/Atmosphere generation
13. Improved rule-based transpiler (strip class/namespace, convert loops)

### Phase 3 — Long Term (Major Features)
14. Vertex color baking (FBX parse → UV map → texture multiply)
15. Multi-material mesh splitting
16. Terrain splat map → MaterialVariant conversion
17. Custom Shader Graph analysis (.shadergraph parsing)
18. Audio source → Sound mapping
19. UI Canvas → ScreenGui mapping

---

## Test Coverage

**Current**: No automated tests exist. The converter has been manually tested against:
- A synthetic platformer game (6 materials, 1 scene, 1 prefab, 2 scripts)
- Trash Dash (72 materials, analysis only — documented in `docs/trash_dash_UNCONVERTED.md`)

**Needed**:
- Unit tests for each module's public API
- Integration test: full pipeline on synthetic project, assert output structure
- Regression test: known-good .rbxl output comparison
