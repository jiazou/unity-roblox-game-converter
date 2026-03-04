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

### ~~P1a: Asset Extraction Crash-on-Error~~

**Status**: RESOLVED (2026-03-04)

**File**: `modules/asset_extractor.py`

| # | Issue | Status |
|---|-------|--------|
| 1 | ~~Zero try/except in file-walk loop~~ | RESOLVED — per-file try/except OSError |
| 2 | ~~`fpath.stat()` and `_sha256_of()` can raise OSError~~ | RESOLVED — wrapped with warnings |

---

### ~~P1b: RBXL Asset ID Patching via str.replace~~

**Status**: RESOLVED (2026-03-04)

**File**: `modules/roblox_uploader.py`

| # | Issue | Location | Status |
|---|-------|----------|--------|
| 1 | ~~`content.replace()` on raw XML~~ | `roblox_uploader.py` | RESOLVED — XML-aware ElementTree patching |
| 2 | ~~`re.IGNORECASE` fallback regex~~ | `roblox_uploader.py` | RESOLVED — only patches `<Content>`/`<url>` elements |
| 3 | ~~HTTP error codes lost~~ | `roblox_uploader.py` | RESOLVED — `_describe_upload_error()` extracts HTTP status codes |

---

## Tier 2: MEDIUM — Silent Data Loss / Incomplete Coverage

### ~~P2a: Code Validator False Positives~~

**Status**: RESOLVED (2026-03-04)

**File**: `modules/code_validator.py`

| # | Issue | Status |
|---|-------|--------|
| 1 | ~~Long strings `[=[...]=]` not handled~~ | RESOLVED — level-N long string support |
| 2 | ~~Comment stripping order wrong~~ | RESOLVED — block comments stripped first |

---

### ~~P2b: Material Mapper Coverage Gaps~~

**Status**: RESOLVED (2026-03-04)

**File**: `modules/material_mapper.py`

| # | Issue | Status |
|---|-------|--------|
| 1 | ~~Missing built-in shaders~~ | RESOLVED — added 10 shaders |
| 2 | ~~YAML tag stripping regex~~ | RESOLVED — multiline-aware regex |
| 3 | ~~Pillow missing silently skipped~~ | RESOLVED — warns when Pillow missing |
| 4 | ~~Blanket except, no logging~~ | RESOLVED — per-texture error logging |
| 5 | ~~Binary specular→metallic threshold~~ | RESOLVED — continuous mapping |
| 6 | ~~Legacy _Shininess clamped to [0,1]~~ | RESOLVED — normalizes 0-128 range |
| 7 | ~~Project-specific shader patterns~~ | RESOLVED — data-driven lookup |
| 8 | Substring-based shader property detection | Accepted risk — conservative fallback for short sources mitigates |

---

### ~~P2c: GUID Resolver~~

**Status**: RESOLVED (2026-03-04)

**File**: `modules/guid_resolver.py`

| # | Issue | Status |
|---|-------|--------|
| 1 | ~~`_extract_parent_guid` regex fails on multi-line refs~~ | RESOLVED — added block-style YAML pattern |
| 2 | ~~Only `.prefab`/`.unity` scanned; `.asset` ignored~~ | RESOLVED — `.asset` files now scanned |
| 3 | ~~No `Library/PackageCache/` awareness~~ | RESOLVED — UPM cache dir now scanned |
| 4 | ~~Dead `import yaml`~~ | RESOLVED — removed |

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
| ~~`mesh_decimator.py:108-113`~~ | ~~OBJ face counter counts `f` lines naively (n-gons undercount)~~ | ~~RESOLVED~~ |
| ~~`mesh_decimator.py:254`~~ | ~~Decimation failure doesn't copy original mesh as fallback~~ | ~~RESOLVED~~ |
| ~~`scriptable_object_converter.py:139`~~ | ~~Silent `yaml.YAMLError` swallowing, no file name logged~~ | ~~RESOLVED~~ |
| `scriptable_object_converter.py:110-111` | Unconditional `m_` prefix stripping on all nested dict keys | MEDIUM |
| `rbxl_writer.py:549-557` | Positional tuple unpacking for light/sound/particle (no named struct) | MEDIUM |

---

## Resolved

### ~~C# → Luau Transpiler Regex Pipeline~~

**Status**: RESOLVED (2026-03-04)
**Commit**: `8494bdd` — Replaced 73+ sequential regex substitutions with AST-driven
tree-sitter emitter (`_LuauEmitter` class). Regex preserved as fallback.
**Skill**: `review-csharp-lua-conversion`
