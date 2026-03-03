# Unsupported Conversions & Known Limitations

> Last updated: 2026-03-03
> Converter version: 0.2.0 (pre-release)
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
| C# → Luau transpilation (AI mode) | Medium | Requires Claude API key |
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
| Rule-based transpiler (improved) | Medium | Braces→end, if/while/for/foreach, Mathf, types, semicolons |
| Collider → Part sizing | High | Box, Sphere, Capsule colliders set part size |
| Rigidbody kinematic detection | High | `m_IsKinematic` → `Anchored` property |

### NOT Supported (Detailed Below)

| Feature | Severity | Fixable? | Section |
|---------|----------|----------|---------|
| Vertex colors | **HIGH** | Partial | [Vertex Colors](#vertex-colors) |
| Multi-material meshes | **HIGH** | Future | [Multi-Material Meshes](#multi-material-meshes) |
| UV tiling ≠ (1,1) | **HIGH** | Partial | [UV Tiling](#uv-tiling-and-offset) |
| Terrain / splat maps | **HIGH** | Future | [Terrain](#terrain-conversion) |
| ~~Height/parallax maps~~ | ~~MEDIUM~~ | ~~Yes~~ | ~~[Height Maps](#heightparallax-maps)~~ FIXED |
| ~~Detail maps~~ | ~~MEDIUM~~ | ~~Yes~~ | ~~[Detail Maps](#detail-maps)~~ FIXED |
| Custom Shader Graph | MEDIUM | Partial | [Shader Graph](#custom-shader-graph) |
| ~~Canvas / UI~~ | ~~MEDIUM~~ | ~~Yes~~ | ~~[UI Canvas](#ui-canvas)~~ FIXED |
| SSS / anisotropy / iridescence | LOW | No | [HDRP Advanced](#hdrp-advanced-features) |

---

## Recently Fixed (Previously Critical)

These issues were listed as critical or high-severity in earlier versions but have since
been resolved. Kept here for historical reference.

### ~~Transform Scale Not Applied~~ — FIXED

Previously all parts received a hardcoded `(4.0, 1.0, 4.0)` size. Now `node_to_part()`
in `conversion_helpers.py` multiplies `node.scale` (from `m_LocalScale`) into part size.

### ~~Materials Not Applied to Plain Parts~~ — FIXED

`apply_materials()` now runs for all parts regardless of mesh presence. `BasePart.Color3`
and `BasePart.Transparency` are set from the material definition. `SurfaceAppearance` is
correctly skipped for plain Parts (Roblox platform limitation).

### ~~Rotation Not Converted~~ — FIXED

Quaternion `(x, y, z, w)` from `m_LocalRotation` is now converted to a full CFrame
rotation matrix via `_quat_to_rotation_matrix()` in `rbxl_writer.py`. Identity rotations
emit a simpler `Position` property for cleaner output.

### ~~Prefab Instances Not Instantiated~~ — FIXED

`resolve_prefab_instances()` in `conversion_helpers.py` resolves `PrefabInstance`
references, inserts prefab node subtrees into the scene, and applies property
modifications from `m_Modifications`.

### ~~Particle Systems Not Converted~~ — FIXED

`convert_particle_components()` extracts rate, lifetime, speed, size, and color from
`ParticleSystem` components and writes `ParticleEmitter` children in the .rbxl output.

### ~~Audio Sources Not Handled~~ — FIXED

`convert_audio_components()` extracts clip path, volume, pitch, loop, play-on-awake,
and distance properties from `AudioSource` components and writes `Sound` children.

### ~~Part Sizing From Transform~~ — FIXED

Part size is now derived from `m_LocalScale`. Collider dimensions (Box, Sphere, Capsule)
override the size when present.

### ~~Directional Light Not Handled~~ — FIXED

`convert_light_components()` now collects directional lights (type 1) and
`directional_lights_to_lighting()` builds a `RbxLightingConfig` that maps Unity's
directional light color and intensity to Roblox `Lighting` service properties
(Brightness, ColorShift_Top, OutdoorAmbient).

### ~~Unity Primitives Not Mapped to Roblox Shapes~~ — FIXED

`_detect_primitive_shape()` identifies Unity built-in primitives (Cube, Sphere,
Cylinder, Capsule, Plane) via their MeshFilter `m_Mesh` reference (GUID
`0000000000000000e000000000000000` + known fileIDs) and sets the Roblox `shape`
property (Block, Ball, Cylinder).

### ~~Normal Map Scale Not Baked~~ — FIXED

When `_BumpScale ≠ 1.0`, the texture processor now bakes the scale into the
normal map by scaling XY components and renormalizing Z, matching the formula
from the material mapping research doc.

### ~~Standard (Specular) Not Converted to Metallic~~ — FIXED

`_convert_material()` now applies the luminance-based specular-to-metallic heuristic
from the research doc: `spec_luminance > 0.5 → metallic=1.0, else 0.0`.

### ~~URP Alpha Mode Not Handled~~ — FIXED

`_parse_material()` now reads URP's `_Surface` + `_AlphaClip` properties when
`_Mode` is absent, correctly mapping `_Surface=0 → Opaque`, `_Surface=1 + _AlphaClip=1
→ Cutout`, `_Surface=1 + _AlphaClip=0 → Transparent`.

### ~~Smoothness from Albedo Alpha Not Supported~~ — FIXED

When `_SmoothnessTextureChannel == 1`, roughness is now extracted from the albedo
texture's alpha channel instead of the metallic texture, matching Unity's behavior.

### ~~HDRP MaskMap Not Parsed~~ — FIXED

`_identify_shader()` now detects HDRP shaders by checking for `_BaseColorMap` and
`_MaskMap` properties. `_parse_material()` handles the MODS packing (R=Metallic,
G=AO, A=Smoothness), and `_convert_material()` extracts each channel correctly.

### ~~Legacy Bumped/Specular Shaders Treated as Simple~~ — FIXED

Legacy Bumped Diffuse and Legacy Specular shaders are now routed through the PBR
pipeline, extracting normal maps and converting specular values to metallic.

### ~~Texture Offset Not Applied~~ — FIXED

When `_MainTex_ST` has non-zero offset values, the texture processor now applies
pixel-level shifting using `PIL.ImageChops.offset()`.

### ~~parts_written Only Counted Root Parts~~ — FIXED

`write_rbxl()` now uses `_count_parts()` to recursively count all parts including
nested children, giving accurate part counts in the conversion report.

---

## Remaining Gaps

### Geometry & Transform

#### ~~Mesh-Based Part Sizing~~ — FIXED

~~**Severity**: MEDIUM~~
~~**Status**: Not implemented~~

Mesh bounding box sizing is now implemented using trimesh AABB. See Recently Fixed.

#### ~~Unity Primitive to Roblox Shape Mapping~~ — FIXED

~~**Severity**: MEDIUM~~
~~**Status**: Not implemented~~

Unity built-in primitives now map to Roblox shape equivalents. See Recently Fixed.

---

### Scene & Object Type Gaps

#### ~~Directional Lights~~ — FIXED

~~**Severity**: MEDIUM~~
~~**Status**: Not implemented~~

Directional lights now map to Roblox `Lighting` service properties. See Recently Fixed.

#### ~~Cameras~~ — FIXED

~~**Severity**: MEDIUM~~
~~**Status**: Not implemented~~

Camera objects are now mapped to `Workspace.CurrentCamera` with FOV, CFrame, and
near/far clip plane configuration. See Recently Fixed.

#### ~~UI Canvas~~ — FIXED

~~**Severity**: MEDIUM~~
~~**Status**: Not implemented~~

Unity Canvas / RectTransform UI hierarchy is now converted to Roblox ScreenGui:
- `Canvas` → `ScreenGui` (placed in `StarterGui`)
- `Text` → `TextLabel` (with text content, size, colour, alignment)
- `Image` / `RawImage` → `ImageLabel` (with sprite GUID, colour tint)
- `Button` → `TextButton` (with text from associated Text component)
- `InputField` → `TextBox`
- `ScrollRect` → `ScrollingFrame`
- Other RectTransform nodes → `Frame`
- Full anchor/pivot/SizeDelta → UDim2 position/size conversion
- Nested hierarchy preserved (parent Frame → child TextLabel etc.)
- Background color extracted from Image components on Frame nodes

See `modules/ui_translator.py` and `modules/rbxl_writer.py`.

#### ~~Skybox and Atmosphere~~ — FIXED

~~**Severity**: MEDIUM~~
~~**Status**: Not converted~~

Unity Skybox materials (6-sided) are now mapped to Roblox `Sky` + `Atmosphere`
objects in Lighting. See Recently Fixed.

---

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

**Remaining limitation**: FBX format is not natively supported by trimesh. Meshes in
FBX format need to be converted to OBJ/GLB first, or processed through a separate
FBX parsing library (pyassimp, Blender Python API) for vertex color extraction.

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

#### ~~Height/Parallax Maps~~ — FIXED

~~**Severity**: MEDIUM~~

Height maps are now converted to normal detail via Sobel filter:
- `_ParallaxMap` / `_HeightMap` → Sobel X/Y gradients → normal vectors
- Strength scaled by `_Parallax` value (typically 0.02–0.1)
- When a base normal map exists, the height-derived normals are UDN-blended in
- When no base normal exists, a new normal map is generated from the height map

The `heightmap_to_normal` texture operation handles both standalone and blend modes.

#### ~~Detail Maps~~ — FIXED

~~**Severity**: MEDIUM~~

Detail maps are now composited into the base textures:
- `_DetailAlbedoMap` → overlay-blended into `ColorMap` (with tiling + mask support)
- `_DetailNormalMap` → UDN-blended into `NormalMap` (with tiling + mask + scale support)
- `_DetailMask` → used as blend weight for both operations

The `composite_detail` and `blend_normal_detail` texture operations handle tiling
(pre-tiling the detail texture) and masking (R channel of `_DetailMask`).

#### Custom Shader Graph

**Severity**: MEDIUM (variable per game)
**Status**: Best-effort property extraction

Custom Shader Graph shaders (.shadergraph) are not parsed. The converter can only
identify custom `.shader` files by parsing their source code for property references
and `#include` resolution.

For Shader Graph materials, the converter falls back to checking if standard property
names (`_BaseMap`, `_Color`) exist in the material's saved properties.

#### ~~Normal Map Scale~~ — FIXED

~~**Severity**: LOW~~
~~**Status**: Not implemented~~

Normal map scale baking is now implemented. See Recently Fixed.

#### ~~Unlit Materials~~ — FIXED

~~**Severity**: LOW~~

Unlit game detection is now implemented. When >70% of materials use unlit shaders
(URP Unlit, Legacy Diffuse, Particle Unlit, etc.), the converter auto-adjusts
`Lighting.Brightness` low and `Lighting.Ambient` high in the .rbxl output.
See Recently Fixed.

---

## Script Transpilation Gaps

### C# to Luau Transpilation Quality

**Severity**: LOW (rule-based mode) / NEGLIGIBLE (AI mode)
**Status**: Rule-based transpiler handles common patterns; AI mode recommended for production

**What rule-based mode handles**:
- Variable declarations (`int/float/bool/string/var/List<T>` → `local`)
- Debug.Log → print
- `void Foo()` → `local function Foo()`
- Unity lifecycle stubs: `Start()` → `AncestryChanged`, `Update()` → `Heartbeat`
- `this.` → `self.`
- Braces `{ }` → `do/then...end` block conversion
- `using` directives and `namespace` wrappers (stripped)
- Class declarations with inheritance (stripped)
- Access modifiers (`public/private/protected/static` etc., stripped)
- Return type annotations on methods (stripped)
- C# type casts (stripped)
- `for(int i=0; i<n; i++)` → `for i = 0, n-1 do`
- `foreach (Type item in collection)` → `for _, item in collection do`
- `while (cond) {` → `while cond do`
- `if/else if/else` chains → `if/elseif/else...then...end`
- `!=` → `~=`, `&&` → `and`, `||` → `or`, `!x` → `not x`
- `null` → `nil`
- Ternary `? :` → `if then else`
- `.Length/.Count` → `#table`
- `.Add/.Remove/.Contains` → `table.insert/remove/find`
- `.ToString()` → `tostring()`
- `Mathf.*` → `math.*` (abs, sin, cos, sqrt, floor, ceil, min, max, clamp, lerp, PI, Infinity)
- `Time.deltaTime` → `dt`
- `new Vector3/Vector2/Color()` → `.new()` constructors
- `new List<T>()/Dictionary<T>()` → `{}`
- String concatenation `+` → `..`
- Semicolons stripped
- Comprehensive API mapping table (50+ Unity API → Roblox equivalents)
- Tree-sitter AST parsing (when available) for structural analysis, service imports, and classification
- `[SerializeField]` fields with prefab refs → `ServerStorage:WaitForChild()`
- Script client/server/module classification based on API usage

**What rule-based mode does NOT handle well**:
- Properties (getters/setters)
- Inheritance / interfaces (class structure stripped, not restructured)
- LINQ expressions
- Coroutines (`IEnumerator`, `yield return`) — APIs mapped but not structurally rewritten
- Complex generic types
- Event subscriptions / delegates

**AI mode** (requires Claude API key): Produces significantly better results —
handles all of the above correctly. Recommended for production.

**Post-transpilation validation**: `code_validator.py` checks generated Luau for
block keyword balance, residual C# syntax, curly braces, trailing semicolons, and
bracket balance. Scripts with validation errors are flagged for review.

---

### `Instantiate()` → `Clone()` Is a Naive Text Substitution

**Severity**: MEDIUM
**Status**: Known limitation — not planned for rule-based fix

The API mapping `Instantiate` → `.Clone` is a simple text substitution, not a
structural rewrite. This means:

| Unity C# | What the transpiler produces | What it should produce |
|---|---|---|
| `Instantiate(prefab)` | `.Clone(prefab)` (broken) | `prefab:Clone(); clone.Parent = workspace` |
| `var x = Instantiate(prefab, pos, rot)` | `local x = .Clone(prefab, pos, rot)` (broken) | `local x = prefab:Clone(); x.CFrame = ...` |
| `Instantiate(prefab, parent)` | `.Clone(prefab, parent)` (broken) | `prefab:Clone(); clone.Parent = parent` |

The `Instantiate` call in Unity is a static method with constructor semantics
(source object, optional position/rotation/parent), while Roblox `Clone()` is an
instance method with no arguments — position and parenting are separate calls. A
correct conversion requires restructuring the expression, not replacing a token.

**Workaround**: Use `--use-ai` mode, which handles this correctly. For rule-based
output, manually replace `.Clone(...)` calls with proper `:Clone()` + property
assignment patterns.

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

### Parts Written Count

~~Previously root-only.~~ **FIXED**: `_count_parts()` now recursively counts all parts
including nested children. The `parts_written` field accurately reflects every Part and
MeshPart written to the .rbxl.

### Materials Processed Count

Materials are only processed if their GUID appears in a scene's or prefab's
`referenced_material_guids`. Materials that exist in the project but aren't referenced
by any scene renderer are silently skipped. The total count in the report reflects
only processed materials, not all `.mat` files found.

---

## Future Roadmap

### Phase 1 — Next Release (Remaining Bugs)
1. ~~Apply Transform scale to Part size~~ — Done
2. ~~Apply material Color3/Transparency to plain Parts~~ — Done
3. ~~Map Unity primitives (Cube/Sphere/Cylinder/Plane) to Roblox shape equivalents~~ — Done
4. ~~Convert rotation quaternion to CFrame~~ — Done
5. ~~Map Directional Light → Roblox `Lighting` properties~~ — Done
6. ~~Instantiate prefabs in scene tree~~ — Done
7. ~~Fix parts_written counting to include children~~ — Done

### Phase 2 — Near Term (Feature Gaps)
8. ~~UV pre-tiling texture processor~~ — Done (offset also implemented)
9. ~~Normal map scale baking~~ — Done
10. ~~Unlit game detection + Lighting configuration~~ — Done
11. ~~Skybox/Atmosphere generation~~ — Done
12. ~~Improved rule-based transpiler~~ — Done (braces→end, if/while/for, types, Mathf, ternary, semicolons)
13. ~~Camera → `Workspace.CurrentCamera` mapping~~ — Done
14. ~~Mesh bounding box → Part size for MeshParts~~ — Done

### Phase 2.5 — Recently Completed
15. ~~Detail map compositing~~ — Done (overlay blend albedo + UDN blend normal + mask + tiling)
16. ~~Height map → normal detail~~ — Done (Sobel filter + optional base normal blend)
17. ~~Vertex color baking~~ — Done (trimesh + barycentric raster + albedo multiply; OBJ/PLY/GLB)
18. ~~UI Canvas → ScreenGui~~ — Done (Text/Image/Button → TextLabel/ImageLabel/TextButton + UDim2)

### Phase 3 — Long Term (Major Features)
19. Multi-material mesh splitting
20. Terrain splat map → MaterialVariant conversion
21. Custom Shader Graph analysis (.shadergraph parsing)

---

## Test Coverage

**Current**: 811 automated tests across 16 test files covering:
- `test_unity_yaml_utils.py` — YAML parsing, vector/quaternion extraction, references
- `test_conversion_helpers.py` — All component conversion helpers (colliders, lights, audio, particles, materials)
- `test_converter.py` — End-to-end node-to-part, prefab resolution, scene conversion, report building
- `test_scene_parser.py` — Scene YAML parsing, hierarchy building
- `test_prefab_parser.py` — Prefab YAML parsing
- `test_material_mapper.py` — Shader property mapping, pipeline detection
- `test_code_transpiler.py` — C# → Luau rule-based transpilation
- `test_api_mappings.py` — API call/type/lifecycle mapping tables
- `test_llm_cache.py` — LLM response caching, TTL, eviction
- `test_retry.py` — Retry logic, backoff, exception handling
- `test_asset_extractor.py` — Asset file discovery
- `test_code_validator.py` — Luau syntax validation

**Still needed**:
- Integration test: full pipeline on synthetic project, assert output structure
- Regression test: known-good .rbxl output comparison

**Infrastructure modules** (implemented, not yet listed in test coverage section above):
- `modules/code_validator.py` — Luau syntax validation (block balance, C# residue, bracket balance)
- `modules/retry.py` — Exponential backoff retry decorator and callable wrapper
- `modules/llm_cache.py` — Hash-based disk cache for LLM responses (SHA-256 keyed, TTL-based eviction)
