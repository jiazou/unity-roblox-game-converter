# Fragility Audit — Unity→Roblox Game Converter

Date: 2026-03-04
Methodology: Tree-sitter AST audit of all pipeline modules for regex-heavy parsing,
silent error swallowing, hardcoded tables, and brittle structural assumptions.

---

## Tier 1: HIGH — Structurally Fragile

### P0: Unity YAML Parsing

**Files**: `modules/unity_yaml_utils.py`, `modules/scene_parser.py`, `modules/prefab_parser.py`

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| 1 | `UNITY_DOC_SEPARATOR` regex `(\d+)` rejects negative fileIDs | `unity_yaml_utils.py:30` | Silently drops all Prefab Variant documents (standard since Unity 2018.3) |
| 2 | No awareness of `stripped` suffix on document separators | `unity_yaml_utils.py:30` | Stripped objects parsed as full → wrong positions, missing names, incorrect defaults |
| 3 | Single `yaml.YAMLError` drops entire file — all-or-nothing | `unity_yaml_utils.py:115-118` | One malformed component in a 500-object scene → empty result, no warning |
| 4 | Positional doc-header pairing via counter | `unity_yaml_utils.py:106-134` | If `yaml.safe_load_all` produces unexpected docs, all subsequent nodes get wrong IDs |
| 5 | Prefab parser component allowlist (4 types) vs scene parser (15 types) | `prefab_parser.py:118-119` | Colliders, rigidbodies, lights, cameras, particles, animators silently lost from prefabs |
| 6 | `doc_body()` returns first dict value found | `unity_yaml_utils.py:138-146` | Custom MonoBehaviour structures with multiple dict-valued top-level keys: wrong data |
| 7 | Header regex assumes exactly 2-line `%YAML\n%TAG` format | `unity_yaml_utils.py:29` | Extra `%TAG` lines or whitespace → header not stripped → parse failure |
| 8 | `m_Materials: null` (YAML None) causes `TypeError: NoneType not iterable` | `scene_parser.py:310` | MeshRenderer with empty materials field crashes node processing |

**Skill**: `harden-unity-yaml-parsing`

---

### P1a: Asset Extraction Crash-on-Error

**File**: `modules/asset_extractor.py`

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| 1 | Zero try/except in file-walk loop | `asset_extractor.py:93-114` | One broken symlink, permission error, or race condition crashes entire extraction |
| 2 | `fpath.stat()` and `_sha256_of()` both can raise `OSError` | `asset_extractor.py:108-109` | Unhandled exception kills the manifest build |

**Skill**: `harden-asset-extraction`

---

### P1b: RBXL Asset ID Patching via str.replace

**File**: `modules/roblox_uploader.py`

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| 1 | `content.replace(f"rbxassetid://{local_name}", rbx_url)` on raw XML | `roblox_uploader.py:311-321` | Replaces ALL occurrences — including inside Luau ProtectedString source blocks |
| 2 | `re.IGNORECASE` fallback regex compounds the problem | `roblox_uploader.py:317` | Case-insensitive match can hit Luau variable names matching asset filenames |
| 3 | HTTP error codes lost — `urllib.error` imported but caught as generic `Exception` | `roblox_uploader.py:389-449` | 401/403/429 errors not distinguishable from network failures |

**Skill**: `fix-rbxl-asset-patching`

---

## Tier 2: MEDIUM — Silent Data Loss / Incomplete Coverage

### P2a: Code Validator False Positives

**File**: `modules/code_validator.py`

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| 1 | Comment/string stripper doesn't handle Luau long strings `[=[...]=]` | `code_validator.py:68-77` | Long strings containing `function`/`if`/`{` cause false block-balance errors |
| 2 | `--` comment stripping runs before `--[[` block comment removal | `code_validator.py:68-77` | `--[[ function foo() ]]` → partial content survives stripping |

**Skill**: `fix-luau-validator-stripping`

---

### P2b: Material Mapper Coverage Gaps

**File**: `modules/material_mapper.py`

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| 1 | `_BUILTIN_SHADERS` missing UI/Default, Unlit/*, Mobile/*, Transparent/* | `material_mapper.py:136-147` | Common shaders fall through to heuristic, may be misclassified |
| 2 | YAML tag stripping via regex (same fragile pattern as unity_yaml_utils) | `material_mapper.py:321-326` | Multi-`%TAG` or reformatted headers cause parse failure |
| 3 | Pillow missing → ALL texture processing silently skipped | `material_mapper.py:1149-1153` | No warning; downstream references dangling texture filenames |
| 4 | Blanket `except Exception: continue` in texture loop, no logging | `material_mapper.py:1504-1506` | Corrupt texture or OOM silently swallowed, texture never generated |
| 5 | Binary specular→metallic threshold (0 or 1, no gradient) | `material_mapper.py:813-843` | All semi-metallic materials collapse to fully metallic or non-metallic |
| 6 | Legacy `_Shininess` clamped to [0,1] — wrong for pre-Unity5 range 0-128 | `material_mapper.py:598-601` | All high-shininess materials become fully smooth |
| 7 | Project-specific custom shader patterns (Curved*, UnlitBlinking) | `material_mapper.py:168-175` | Useless for any other project |
| 8 | Substring-based shader property detection (`"_Color" in full_source`) | `material_mapper.py:245-250` | Matches in comments/variable names; misses unconventional aliases |

**Skill**: `review-material-mapper-coverage`

---

### P2c: GUID Resolver

**File**: `modules/guid_resolver.py`

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| 1 | `_extract_parent_guid` regex `[^}]*` fails on multi-line serialized refs | `guid_resolver.py:211` | Prefab variant chain resolution silently stops early |
| 2 | Only `.prefab`/`.unity` scanned for parent refs; `.asset` ignored | `guid_resolver.py:204` | ScriptableObject prefab references invisible |
| 3 | No `Library/PackageCache/` awareness for UPM packages | `guid_resolver.py:251-255` | All UPM package asset references resolve to None |
| 4 | Dead `import yaml` — imported but never used | `guid_resolver.py:31` | Code smell; suggests intended YAML parsing was never implemented |

---

## Tier 3: LOW-MEDIUM — Maintenance Hazards

### P3: Divergent Extension Maps

**Files**: `modules/guid_resolver.py`, `modules/asset_extractor.py`, `config.py`

Three different `_EXT_TO_KIND` / `SUPPORTED_ASSET_EXTENSIONS` maps with different entries:

| Extension | `guid_resolver` | `asset_extractor` | `config.py` |
|-----------|-----------------|-------------------|-------------|
| `.exr` | ✓ texture | ✗ | ✗ |
| `.hdr` | ✓ texture | ✗ | ✗ |
| `.psd` | ✓ texture | ✗ | ✗ |
| `.blend` | ✓ mesh | ✗ | ✗ |
| `.shader` | ✓ shader | ✗ | ✗ |
| `.prefab` | ✓ prefab | ✗ | ✗ |
| `.unity` | ✓ scene | ✗ | ✗ |
| `.cs` | ✓ script | ✗ | ✗ |
| `.asset` | ✗ | ✗ | ✓ |

**Skill**: `consolidate-asset-type-maps`

---

### Other Notable Issues (not skill-worthy individually)

| Module | Issue | Severity |
|--------|-------|----------|
| `ui_translator.py:221-222` | Hardcoded partial GUID prefix for Image component detection | MEDIUM |
| `ui_translator.py:122-127` | 4-entry font map, no fallback warning | MEDIUM |
| `mesh_decimator.py:108-113` | OBJ face counter counts `f` lines naively (n-gons undercount) | MEDIUM |
| `mesh_decimator.py:254` | Decimation failure doesn't copy original mesh as fallback | MEDIUM |
| `scriptable_object_converter.py:139` | Silent `yaml.YAMLError` swallowing, no file name logged | HIGH |
| `scriptable_object_converter.py:110-111` | Unconditional `m_` prefix stripping on all nested dict keys | MEDIUM |
| `rbxl_writer.py:549-557` | Positional tuple unpacking for light/sound/particle (no named struct) | MEDIUM |

---

## Resolved

### ~~C# → Luau Transpiler Regex Pipeline~~

**Status**: RESOLVED (2026-03-04)
**Commit**: `8494bdd` — Replaced 73+ sequential regex substitutions with AST-driven
tree-sitter emitter (`_LuauEmitter` class). Regex preserved as fallback.
**Skill**: `review-csharp-lua-conversion`
