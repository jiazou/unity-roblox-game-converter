# Module Status — Unity→Roblox Game Converter

> Last updated: 2026-03-04
> Consolidates: FRAGILITY_AUDIT.md, component_analysis_comparison.md,
> function_spec_review.md, material_converter_plan.md, sprites-audio-ui-fix-plan.md

---

## Table of Contents

| # | Module | Status |
|---|--------|--------|
| [1](#1-scene-parsing) | Scene Parsing | Fully implemented (15 component types, per-doc error recovery) |
| [2](#2-asset-discovery--guid-resolution) | Asset Discovery & GUID Resolution | Fully implemented (1 low-severity gap: divergent extension maps) |
| [3](#3-material-mapping) | Material Mapping | Fully implemented (5 remaining gaps: multi-mat, UV >4x, Shader Graph, FBX vertex colors, terrain) |
| [4](#4-code-transpilation) | Code Transpilation | Fully implemented (AI transpilation via Claude; 5 low/medium gaps) |
| [5](#5-mesh-processing) | Mesh Processing | Fully implemented (no remaining gaps) |
| [6](#6-ui-translation) | UI Translation | Fully implemented (3 remaining gaps: sprite pipeline, GUID detection, font map) |
| [7](#7-rbxl-output) | RBXL Output | Fully implemented (3 low/medium gaps) |
| [8](#8-upload--reporting) | Upload & Reporting | Fully implemented (no remaining gaps) |
| [9](#9-orchestration) | Orchestration | Fully implemented (2 low gaps) |
| [10](#10-infrastructure) | Infrastructure | Fully implemented |
| [11](#11-scriptableobject-conversion) | ScriptableObject Conversion | Fully implemented (1 medium gap) |
| [12](#12-roblox-platform-limitations) | Roblox Platform Limitations | 12 permanent engine-level restrictions |
| [13](#13-deferred-features) | Deferred Features | 12 features tracked (P1–P3) |
| [14](#14-test-coverage) | Test Coverage | 811 tests across 16 files |

### Related Documents (Not Consolidated)

| Document | Purpose |
|----------|---------|
| `docs/UNSUPPORTED.md` | Living document of unsupported conversions, known limitations, and what's fully supported |
| `docs/material_mapping_research.md` | Design specification — full Unity→Roblox property mapping reference (862 lines) |
| `docs/smartdown_template.md` | Template specification — UNCONVERTED.md file structure and data contracts |
| `docs/trash_dash_full_gap_analysis.md` | End-to-end gap analysis of converter vs Trash Dash game requirements |
| `docs/trash_dash_UNCONVERTED.md` | Per-material conversion analysis for Trash Dash (72 materials, 13 shaders) |

---

## 1. Scene Parsing

**Files**: `modules/scene_parser.py`, `modules/prefab_parser.py`, `modules/unity_yaml_utils.py`

**What it does**: Parses Unity `.unity` scene files and `.prefab` files (custom YAML format
with `%TAG !u!` directives and `--- !u!<classID> &<fileID>` document separators). Builds a
`SceneNode` hierarchy with Transform position/rotation/scale, component data, material
references, and parent-child relationships. Resolves prefab instances and applies
`m_Modifications`.

### Status: Fully Implemented

- Per-document YAML parsing with individual error recovery
- Shared `KNOWN_COMPONENT_CIDS` frozenset (15 component types) used by both parsers
- Negative fileID support in document separators (`(-?\d+)`)
- `stripped` suffix detection and filtering
- `m_Materials: null` guarded with `or []`
- Prefab instance resolution with `m_Modifications` property overrides
- Extracts: Transform, MeshFilter, MeshRenderer, Camera, Light, AudioSource,
  ParticleSystem, BoxCollider, SphereCollider, CapsuleCollider, Rigidbody,
  Canvas, RectTransform, MonoBehaviour

### Remaining Gaps

| Gap | Severity | Notes |
|-----|----------|-------|
| Animator Controller (classID 91) not parsed | MEDIUM | State machines, blend trees not extracted. Manual re-animation needed. |
| AnimationClip (classID 74) not extracted | MEDIUM | `.anim` files discovered but not processed |
| CharacterController (classID 143) not recognized | LOW | Roblox Humanoid is fundamentally different; manual rewrite needed |
| MeshCollider (classID 64) not converted | LOW | Complex mesh-based collision has no direct Roblox equivalent |

### Accepted Risks

- `doc_body()` returns first dict value found — Unity documents always have exactly one
  top-level class-name key
- Header regex assumes exactly 2-line `%YAML\n%TAG` format — standard Unity files follow
  this format; regex is intentionally conservative

### Resolved Issues

<details>
<summary>8 issues resolved (2026-03-04)</summary>

| Issue | Resolution |
|-------|------------|
| `UNITY_DOC_SEPARATOR` regex rejected negative fileIDs | Regex uses `(-?\d+)` for both classID and fileID |
| No awareness of `stripped` suffix | Detected and filtered during assembly |
| Single `yaml.YAMLError` dropped entire file | Per-document `yaml.safe_load()` with individual error recovery |
| Positional doc-header pairing via counter | Manual `_split_yaml_documents()` with pre-scanned separators |
| Prefab parser had 4-type allowlist vs scene parser 15 | Shared `KNOWN_COMPONENT_CIDS` frozenset |
| `m_Materials: null` caused TypeError | `or []` guard |
| Rotation not written to .rbxl | Quaternion→CFrame conversion added |
| Scale not applied from Unity | `node.scale` used instead of hardcoded (4,1,4) |

</details>

---

## 2. Asset Discovery & GUID Resolution

**Files**: `modules/asset_extractor.py`, `modules/guid_resolver.py`, `config.py`

**What it does**: Walks the Unity project's `Assets/` directory to catalog all asset files
by type (texture, mesh, audio, script, etc.) with SHA-256 hashes. Builds a bidirectional
GUID↔path index from `.meta` files, supporting chain resolution for nested references.

### Status: Fully Implemented

- Per-file try/except for OSError during file walk
- `.asset` files now scanned
- UPM `Library/PackageCache/` directory scanned
- Block-style YAML pattern for multi-line references

### Remaining Gaps

| Gap | Severity | Notes |
|-----|----------|-------|
| Divergent extension maps across 3 files | LOW | `guid_resolver._EXT_TO_KIND`, `asset_extractor`, and `config.SUPPORTED_ASSET_EXTENSIONS` have different entries. See table below. |

**Extension map divergence**:

| Extension | `guid_resolver` | `asset_extractor` | `config.py` |
|-----------|-----------------|-------------------|-------------|
| `.exr`, `.hdr`, `.psd` | ✓ texture | ✗ | ✗ |
| `.blend` | ✓ mesh | ✗ | ✗ |
| `.shader` | ✓ shader | ✗ | ✗ |
| `.prefab`, `.unity`, `.cs` | ✓ | ✗ | ✗ |
| `.asset` | ✗ | ✗ | ✓ |

### Resolved Issues

<details>
<summary>6 issues resolved (2026-03-04)</summary>

| Issue | Resolution |
|-------|------------|
| Zero try/except in asset extractor file-walk loop | Per-file try/except OSError |
| `fpath.stat()` and `_sha256_of()` could raise OSError | Wrapped with warnings |
| `_extract_parent_guid` regex failed on multi-line refs | Added block-style YAML pattern |
| Only `.prefab`/`.unity` scanned; `.asset` ignored | `.asset` files now scanned |
| No `Library/PackageCache/` awareness | UPM cache dir now scanned |
| Dead `import yaml` in guid_resolver | Removed |

</details>

---

## 3. Material Mapping

**Files**: `modules/material_mapper.py` (~1,206 lines), `modules/vertex_color_baker.py`

**What it does**: Parses Unity `.mat` files, identifies shaders (Standard, URP Lit/Unlit,
HDRP Lit, Legacy, Particle, custom), extracts PBR properties, and converts them to Roblox
`SurfaceAppearance` definitions. Processes textures (channel extraction, inversion, AO
baking, pre-tiling, detail compositing, height-to-normal, vertex color baking). Generates
`UNCONVERTED.md` reports.

### Status: Fully Implemented

The most thorough module in the codebase. Handles:

- **Shaders**: Built-in Standard, Standard (Specular), URP Lit/Unlit, HDRP Lit (MaskMap
  MODS packing), Legacy Diffuse/Bumped/Specular, Particle, Sprite, custom shaders
  (source parsing + `#include` resolution)
- **Textures**: Copy, channel extraction (R/G/B/A), inversion (smoothness→roughness),
  AO baking, pre-tiling (≤4x), offset pixel shifting, grayscale, threshold alpha,
  detail compositing (overlay blend + UDN normal blend), height→normal (Sobel filter),
  normal scale baking
- **Vertex colors**: Barycentric rasterization to UV-space texture, multiply into albedo
  (OBJ/PLY/GLB formats; FBX requires external conversion)
- **Special features**: Ghost property detection (only converts properties the shader
  actually reads), companion Luau scripts for animated shaders (blink, rotation),
  unlit game detection (auto-adjusts Lighting when >70% unlit shaders), skybox material
  → Roblox Sky object
- **Both `.mat` YAML formats**: serializedVersion 2 and 3

### Remaining Gaps

| Gap | Severity | Notes |
|-----|----------|-------|
| Multi-material meshes | HIGH | Roblox: 1 material per MeshPart. Converter uses first material. Future: split geometry at material boundaries. |
| UV tiling > 4x | HIGH | Pre-tiling degrades quality. Needs mesh UV modification for high tiling factors. |
| Custom Shader Graph (.shadergraph) | MEDIUM | Not parsed. Falls back to checking standard property names in saved properties. |
| Vertex colors from FBX format | MEDIUM | trimesh doesn't natively support FBX vertex colors. Needs pyassimp or Blender. |
| Terrain splat maps | HIGH | Requires MaterialVariant per layer + voxel painting. Phase 3 feature. |

### Accepted Risks

- Substring-based shader property detection — conservative fallback for short sources mitigates

### Resolved Issues

<details>
<summary>7 issues resolved (2026-03-04)</summary>

| Issue | Resolution |
|-------|------------|
| Missing built-in shaders | Added 10 shaders |
| YAML tag stripping regex | Multiline-aware regex |
| Pillow missing silently skipped | Warns when Pillow missing |
| Blanket except, no logging | Per-texture error logging |
| Binary specular→metallic threshold | Continuous mapping |
| Legacy _Shininess clamped to [0,1] | Normalizes 0-128 range |
| Project-specific shader patterns | Data-driven lookup |

</details>

**Reference docs**: `docs/material_mapping_research.md` (862 lines — full property-by-property
mapping specification), `docs/smartdown_template.md` (UNCONVERTED.md template structure)

---

## 4. Code Transpilation

**Files**: `modules/code_transpiler.py`, `modules/code_validator.py`, `modules/api_mappings.py`

**What it does**: Converts Unity C# scripts to Roblox Luau using Claude AI. Validates output Luau
for syntax errors. Classifies scripts as LocalScript/Script/ModuleScript based on API usage.

### Status: Fully Implemented

**AI transpilation** (Claude API):
- Each C# script is sent to Claude with the Unity Bridge API reference as context
- Handles architectural adaptation: MonoBehaviour → Luau module, lifecycle hooks, component queries
- Coroutines: `IEnumerator`/`yield return` → `task.spawn` / `task.wait`
- Event subscriptions: `+=`/`-=` on delegates → `:Connect(handler)`
- String interpolation, lambda/anonymous delegates, LINQ expressions
- 50+ Unity API → Roblox mappings (informed by `api_mappings.py`), automatic service imports
- Script classification: Input/Camera/GUI → LocalScript, Command/SyncVar → Script, utility → ModuleScript
- `[SerializeField]` fields with prefab refs → `ServerStorage:WaitForChild()`
- Inheritance, interfaces, complex generics handled correctly

**Code validator**:
- Block keyword balance (`function/if/for/while/repeat` vs `end/until`)
- Residual C# syntax detection, stray curly braces, trailing semicolons
- Level-N long string support (`[=[...]=]`)
- Comments and strings stripped before analysis

### Remaining Gaps

| Gap | Severity | Notes |
|-----|----------|-------|
| Networking attributes (`[Command]`, `[ClientRpc]`, `[SyncVar]`) | MEDIUM | Detected for classification but not converted to RemoteEvent/RemoteFunction patterns |
| Object pooling patterns | LOW | Individual API calls transpile but structural pool management needs manual refactoring |

### ~~Fragile Areas~~ — All Resolved (2026-03-04)

#### ~~4a. Non-AI Fallback Pipeline~~ — REMOVED

**Resolution**: Rule-based and AST transpilers have been removed. All transpilation now uses Claude AI exclusively.

#### ~~4b. Script Type Classification~~

**Resolution**: Expanded `_CLIENT_INDICATORS` (added Cursor, EventSystem, Slider, Toggle, InputField, more Camera/Input patterns) and `_SERVER_INDICATORS` (added `[ServerRpc]`, `[Server]`, Physics, more PlayerPrefs). Client-side lifecycle hooks now weighted 2x. Added `StateMachineBehaviour` to behaviour base classes.

#### ~~4c. Confidence Scoring~~

**Resolution**: Extracted shared `_compute_confidence()` function used by both AST and regex paths. Now penalizes residual C# artifacts (braces, `class` keyword), placeholder comments (TODO/manual/no direct), and warning count.

#### ~~4d. API Mapping Placeholders~~

**Resolution**: Replaced ~20 `-- comment` placeholder entries with real Roblox implementations:
- `PlayerPrefs.*` → `DataStoreService:GetDataStore('PlayerPrefs'):SetAsync/GetAsync`
- `Animator.SetBool/SetFloat` → `:SetAttribute`, `Animator.SetTrigger/Play` → `AnimationTrack:Play()`
- `SceneManager.LoadScene` → `TeleportService:Teleport`
- `[Command]` → `RemoteEvent:FireServer`, `[ClientRpc]` → `RemoteEvent:FireAllClients`, `[SyncVar]` → `:SetAttribute`
- `AddComponent` → `Instance.new`, `Mathf.Lerp` → `math.lerp`
- `Random.insideUnitSphere` → `Random.new():NextUnitVector()`, `RectTransform` → `UDim2`
- And others (Vector3.Angle, MoveTowards, ClampMagnitude, etc.)

#### ~~4e. Event Detection Heuristic~~

**Resolution**: Expanded `_looks_like_event_target` from 8 hardcoded suffixes to a comprehensive approach: 20+ known Roblox/Unity event names (exact match), `On*` prefix with uppercase-third-char guard (avoids `OnGround` false positives), and pattern suffixes (`Event`, `Changed`, `Completed`, `Started`, `Ended`, `Triggered`, `Clicked`, `Pressed`, `Released`).

### Resolved Issues

<details>
<summary>6 issues resolved (2026-03-04)</summary>

| Issue | Resolution |
|-------|------------|
| 73+ sequential regex substitutions (brittle) — commit `8494bdd` | Replaced by AI transpilation via Claude API |
| Coroutines not handled — commit `2fcfe3a` | `_emit_yield_statement` + `task.spawn` wrapping for IEnumerator methods |
| Event subscriptions not handled — commit `2fcfe3a` | `_emit_assignment_expression` detects event-like targets, emits `:Connect()` |
| String interpolation not handled — commit `2fcfe3a` | `_emit_interpolated_string_expression` → `string.format()` |
| Lambda/anonymous delegates not handled — commit `2fcfe3a` | `_emit_lambda_expression` / `_emit_anonymous_method_expression` → `function() end` |
| Code validator false positives (long strings, comment order) | Level-N long string support; block comments stripped first |

</details>

---

## 5. Mesh Processing

**File**: `modules/mesh_decimator.py`

**What it does**: Reduces mesh face count to ≤10K faces (Roblox MeshPart limit) using
quadric decimation via trimesh. Conservative approach: meshes under the limit are copied
unchanged, quality floor of 60%, targets 8K faces (leaving headroom).

### Status: Fully Implemented

- Mesh bounding box → Part size via trimesh AABB
- Unity primitives (Cube/Sphere/Cylinder/Plane) detected via known GUIDs and mapped
  to Roblox shape equivalents (Block/Ball/Cylinder)
- Decimation failure copies original mesh as fallback

### Remaining Gaps

None for current scope. Multi-material mesh splitting (future Phase 3) would interact
with this module.

### Resolved Issues

<details>
<summary>2 issues resolved (2026-03-04)</summary>

| Issue | Resolution |
|-------|------------|
| OBJ face counter counted `f` lines naively (n-gon undercount) | Fixed face counting |
| Decimation failure didn't copy original mesh as fallback | Now copies original on failure |

</details>

---

## 6. UI Translation

**File**: `modules/ui_translator.py`

**What it does**: Converts Unity Canvas/UGUI hierarchy to Roblox ScreenGui elements.
Handles RectTransform anchor/pivot/sizeDelta → UDim2 conversion with Y-axis inversion.

### Status: Fully Implemented

- Canvas → ScreenGui (placed in StarterGui)
- Text → TextLabel (with content, size, colour, alignment)
- Image / RawImage → ImageLabel (with sprite GUID, colour tint)
- Button → TextButton
- InputField → TextBox
- ScrollRect → ScrollingFrame
- Other RectTransform nodes → Frame
- Full anchor/pivot/SizeDelta → UDim2 position/size conversion
- Nested hierarchy preserved
- Background color extracted from Image components on Frame nodes

### Remaining Gaps

| Gap | Severity | Notes |
|-----|----------|-------|
| Sprite asset pipeline incomplete | MEDIUM | Sprites referenced by GUID but not sliced from spritesheets or copied to build output. ImageLabel URLs are placeholders. |
| Hardcoded partial GUID prefix for Image component detection | MEDIUM | `ui_translator.py:221-222` — fragile detection method |
| 4-entry font map, no fallback warning | LOW | `ui_translator.py:122-127` — limited font coverage |

### Resolved Issues

<details>
<summary>3 issues resolved (2026-03-04)</summary>

| Issue | Resolution |
|-------|------------|
| No UI translation at all | Full `ui_translator.py` with Canvas→ScreenGui pipeline |
| UI classification bug (all elements became Frame) | GUID-based MonoBehaviour component detection |
| RectTransform → UDim2 not implemented | Full anchor/pivot/sizeDelta conversion with Y-axis inversion |

</details>

---

## 7. RBXL Output

**File**: `modules/rbxl_writer.py`

**What it does**: Generates valid Roblox `.rbxl` XML files with Parts, MeshParts,
SurfaceAppearance, Scripts, Lighting, ScreenGui, Sound, ParticleEmitter, PointLight,
SpotLight, and Camera objects.

### Status: Fully Implemented

- Quaternion → CFrame rotation matrix via `_quat_to_rotation_matrix()`
- Identity rotations emit simpler Position property
- SurfaceAppearance child elements with full PBR maps
- Script placement: ServerScriptService, StarterPlayerScripts, ReplicatedStorage
- Lighting service properties from directional light conversion
- Skybox/Atmosphere objects in Lighting
- Recursive part counting for accurate report stats
- Sound, ParticleEmitter, PointLight, SpotLight as child objects

### Remaining Gaps

| Gap | Severity | Notes |
|-----|----------|-------|
| Positional tuple unpacking for light/sound/particle | MEDIUM | `rbxl_writer.py:549-557` — no named struct, fragile ordering |
| No `.rbxm` output option | LOW | Would allow merging converted content into existing Roblox places |
| Audio SoundId uses local paths | LOW | Needs upload step to get `rbxassetid://` URLs |

---

## 8. Upload & Reporting

**Files**: `modules/roblox_uploader.py`, `modules/report_generator.py`

**What it does**: Uploads `.rbxl` place files and textures to Roblox Open Cloud API.
Generates `conversion_report.json` with asset counts, material stats, script results,
scene stats, errors/warnings, and timing. Generates `UNCONVERTED.md` transparency reports.

### Status: Fully Implemented

- XML-aware ElementTree patching for asset IDs (replaced fragile `str.replace()`)
- Rate limit header parsing (`x-ratelimit-remaining`/`x-ratelimit-reset`)
- Proactive sleep when approaching rate limits
- Pre-upload payload size validation (20 MB assets, 100 MB places)
- `_describe_upload_error()` extracts HTTP status codes
- HTTP 429 added to retryable exceptions

### Remaining Gaps

None for current scope.

### Resolved Issues

<details>
<summary>6 issues resolved (2026-03-04)</summary>

| Issue | Resolution |
|-------|------------|
| `content.replace()` on raw XML | XML-aware ElementTree patching |
| `re.IGNORECASE` fallback regex | Only patches `<Content>`/`<url>` elements |
| HTTP error codes lost | `_describe_upload_error()` extracts status codes |
| No rate limit header parsing | `_check_rate_limit_headers()` added |
| No payload size validation | Pre-upload size checks (20 MB / 100 MB) |
| HTTP 429 not retried | Added to retryable exceptions |

</details>

---

## 9. Orchestration

**Files**: `converter.py` (batch CLI), `convert_interactive.py` (phase-based CLI for
`/convert-unity` skill)

**What it does**: Coordinates the 5-phase pipeline: Discovery → Inventory → Processing →
Assembly → Upload. The interactive orchestrator stores state in `.convert_state.json` for
phase-by-phase execution with human decision points.

### Status: Fully Implemented

- 5-phase sequential pipeline with Click CLI
- Interactive skill presents flagged materials, scripts, and mesh warnings for review
- Confidence-based script flagging (`flagged_for_review` on TranspiledScript)
- Phase state persistence for resume capability
- Component conversion helpers: colliders, lights, audio, particles, materials,
  cameras, skybox, primitives

### Pipeline Order

```
Phase 1 — Discovery:        scene_parser → prefab_parser
Phase 2 — Inventory:        asset_extractor + guid_resolver + prefab instance resolution
Phase 3 — Heavy processing: material_mapper + code_transpiler + mesh_decimator + scriptable_object_converter
Phase 4 — Assembly:         rbxl_writer + ui_translator
Phase 5 — Upload:           roblox_uploader + report_generator
```

### Remaining Gaps

| Gap | Severity | Notes |
|-----|----------|-------|
| No parallel execution | LOW | Material mapping and code transpilation could run concurrently |
| Additive scene loading not handled | LOW | Unity's multi-scene workflow → Roblox has single Place model |

---

## 10. Infrastructure

**Files**: `modules/retry.py`, `modules/llm_cache.py`, `config.py`

### retry.py — Fully Implemented

- `@retry_with_backoff()` decorator with configurable max_retries, base_delay, max_delay
- `call_with_retry()` callable wrapper
- Handles `ConnectionError`, `TimeoutError`, `OSError`, `urllib.error.URLError/HTTPError`

### llm_cache.py — Fully Implemented

- SHA-256 hash of prompt+model as cache key
- JSON file-per-entry storage with TTL-based expiration (default 7 days)
- `CacheStats` tracking (hits, misses, evictions, writes, hit rate)
- Disabled mode (pass-through) for testing

### config.py — Fully Implemented

Key settings: `TEXTURE_MAX_RESOLUTION=4096`, `TEXTURE_OUTPUT_FORMAT="png"`,
`PRE_TILE_MAX_FACTOR=4`, face target/quality floor for decimation.

---

## 11. ScriptableObject Conversion

**File**: `modules/scriptable_object_converter.py`

**What it does**: Parses Unity `.asset` files containing serialized ScriptableObject data
and converts them to Luau data tables as ModuleScripts in ReplicatedStorage.

### Status: Fully Implemented

### Remaining Gaps

| Gap | Severity | Notes |
|-----|----------|-------|
| Unconditional `m_` prefix stripping on all nested dict keys | MEDIUM | `scriptable_object_converter.py:110-111` — may strip legitimate prefixes |

### Resolved Issues

<details>
<summary>1 issue resolved (2026-03-04)</summary>

| Issue | Resolution |
|-------|------------|
| Silent `yaml.YAMLError` swallowing, no file name logged | Error logging with file name |

</details>

---

## 12. Roblox Platform Limitations

These are engine-level restrictions that **cannot be worked around**:

| Limitation | Impact |
|------------|--------|
| No custom shaders | Vertex shader effects (world curve, wave) cannot be replicated |
| 1 material per MeshPart | Multi-material meshes must be split |
| UV0 only | Secondary UV channels (lightmaps on UV1) are lost |
| No height/displacement mapping | Parallax effects converted to normal detail (approximation) |
| No SSS / anisotropy / iridescence / clear coat | HDRP advanced materials simplified |
| No per-material cubemap reflections | Engine uses environment probes |
| Max 4096×4096 texture | Textures larger than this are downscaled |
| SurfaceAppearance on MeshPart only | Primitive Parts can't use PBR textures |
| No runtime SurfaceAppearance changes | Material animation requires BasePart.Color workaround |
| No SurfaceAppearance tiling/offset | Repeating textures need pre-tiling or UV modification |
| 10,000 face limit per MeshPart | High-poly meshes need decimation |
| No vertex color reading | Vertex colors in mesh data ignored by SurfaceAppearance (baking workaround available) |

---

## 13. Deferred Features

Features not yet implemented, tracked for future work:

| Feature | Priority | Notes |
|---------|----------|-------|
| Animation system (Animator/AnimationClip) | P1 | Requires bone retargeting (Unity Humanoid → Roblox R15/R6). Manual re-animation recommended. |
| Multi-material mesh splitting | P1 | Parse FBX sub-meshes, split geometry at material boundaries |
| Terrain splat map → MaterialVariant | P2 | Create MaterialVariants per splat layer, paint voxels from splat weights |
| Custom Shader Graph (.shadergraph) parsing | P2 | Extract exposed properties and node connections |
| Networking adapter (RemoteEvent generation) | P2 | Detect `[Command]`/`[ClientRpc]` → generate RemoteEvent/RemoteFunction boilerplate |
| `.rbxm` output format | P2 | Alternative output for merging into existing Roblox places |
| Sprite extraction from spritesheets | P2 | Read `.meta` sprite rects, slice with PIL, wire into UI elements |
| Audio file upload pipeline | P2 | Copy audio to build output, upload to Roblox, patch SoundId in .rbxl |
| Texture atlasing | P3 | Not needed for Roblox's per-MeshPart material model |
| Rojo integration | P3 | Direct .rbxl output is sufficient; Rojo adds deployment dependency |
| Prompt template manager | P3 | Only one LLM call site currently; needed when more are added |
| LLM cost estimator | P3 | Nice-to-have for budget planning |

---

## 14. Test Coverage

**811 automated tests** across 16 test files:

| Test File | Coverage Area |
|-----------|--------------|
| `test_unity_yaml_utils.py` | YAML parsing, vector/quaternion extraction, references |
| `test_conversion_helpers.py` | Component conversion helpers (colliders, lights, audio, particles, materials) |
| `test_converter.py` | End-to-end node-to-part, prefab resolution, scene conversion, report building |
| `test_scene_parser.py` | Scene YAML parsing, hierarchy building |
| `test_prefab_parser.py` | Prefab YAML parsing |
| `test_material_mapper.py` | Shader property mapping, pipeline detection |
| `test_code_transpiler.py` | C# → Luau AI transpilation |
| `test_api_mappings.py` | API call/type/lifecycle mapping tables |
| `test_llm_cache.py` | LLM response caching, TTL, eviction |
| `test_retry.py` | Retry logic, backoff, exception handling |
| `test_asset_extractor.py` | Asset file discovery |
| `test_code_validator.py` | Luau syntax validation |

**Still needed**:
- Integration test: full pipeline on synthetic project, assert output structure
- Regression test: known-good .rbxl output comparison

