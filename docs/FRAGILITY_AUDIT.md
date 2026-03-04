# Fragility Audit — Unity→Roblox Game Converter

Date: 2026-03-04
Methodology: Tree-sitter AST audit of all pipeline modules for regex-heavy parsing,
silent error swallowing, hardcoded tables, and brittle structural assumptions.

---

## Tier 1: HIGH — Structurally Fragile

### ~~P0: Unity YAML Parsing~~

**Status**: RESOLVED (2026-03-04)

**Files**: `modules/unity_yaml_utils.py`, `modules/scene_parser.py`, `modules/prefab_parser.py`

| # | Issue | Status |
|---|-------|--------|
| 1 | ~~`UNITY_DOC_SEPARATOR` regex `(\d+)` rejects negative fileIDs~~ | RESOLVED — regex now uses `(-?\d+)` for both classID and fileID |
| 2 | ~~No awareness of `stripped` suffix on document separators~~ | RESOLVED — `stripped` suffix detected and documents filtered during assembly |
| 3 | ~~Single `yaml.YAMLError` drops entire file — all-or-nothing~~ | RESOLVED — per-document `yaml.safe_load()` with individual error recovery |
| 4 | ~~Positional doc-header pairing via counter~~ | RESOLVED — manual `_split_yaml_documents()` replaces `safe_load_all`; pre-scanned separators match 1:1 |
| 5 | ~~Prefab parser component allowlist (4 types) vs scene parser (15 types)~~ | RESOLVED — shared `KNOWN_COMPONENT_CIDS` frozenset (15 types) imported by both parsers |
| 6 | `doc_body()` returns first dict value found | Accepted risk — Unity documents always have exactly one top-level class-name key |
| 7 | Header regex assumes exactly 2-line `%YAML\n%TAG` format | Accepted risk — standard Unity files follow exact format; regex is intentionally conservative |
| 8 | ~~`m_Materials: null` (YAML None) causes `TypeError: NoneType not iterable`~~ | RESOLVED — `or []` guard handles both missing keys and explicit None values |

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

## ~~P4: Transpiler — Remaining Fragile Areas (Skill Candidates)~~

**Status**: RESOLVED (2026-03-04)
**File**: `modules/code_transpiler.py`, `modules/api_mappings.py`

### ~~4a. Regex Fallback Pipeline~~

**Resolution**: Restructured fallback chain to AST → AI → regex. When tree-sitter
fails but an API key is available, the transpiler now escalates to AI rather than
falling through to the fragile regex pipeline. Regex is now a last resort only
when both tree-sitter and AI are unavailable.

### ~~4b. Script Type Classification~~

**Resolution**: Expanded `_CLIENT_INDICATORS` (added Cursor, EventSystem, Slider,
Toggle, InputField, more Camera/Input patterns) and `_SERVER_INDICATORS` (added
`[ServerRpc]`, `[Server]`, Physics, more PlayerPrefs). Client-side lifecycle hooks
now weighted 2x. Added `StateMachineBehaviour` to behaviour base classes.

### ~~4c. Confidence Scoring~~

**Resolution**: Extracted shared `_compute_confidence()` function used by both AST
and regex paths. Now penalizes residual C# artifacts (braces, `class` keyword),
placeholder comments (TODO/manual/no direct), and warning count. Penalties offset
the arbitrary bonuses, producing scores that better reflect actual output quality.

### ~~4d. API Mapping Placeholders~~

**Resolution**: Replaced ~20 `-- comment` placeholder entries with real Roblox
implementations:
- `PlayerPrefs.*` → `DataStoreService:GetDataStore('PlayerPrefs'):SetAsync/GetAsync`
- `Animator.SetBool/SetFloat` → `:SetAttribute` (store params as attributes)
- `Animator.SetTrigger/Play` → `AnimationTrack:Play()`
- `SceneManager.LoadScene` → `TeleportService:Teleport`
- `[Command]` → `RemoteEvent:FireServer`
- `[ClientRpc]` → `RemoteEvent:FireAllClients`
- `[SyncVar]` → `:SetAttribute`
- `AddComponent` → `Instance.new`
- `Mathf.Lerp` → `math.lerp`
- `Random.insideUnitSphere` → `Random.new():NextUnitVector()`
- `RectTransform` → `UDim2`
- And others (Vector3.Angle, MoveTowards, ClampMagnitude, etc.)

### ~~4e. Event Detection Heuristic~~

**Resolution**: Expanded `_looks_like_event_target` from 8 hardcoded suffixes to a
comprehensive approach: 20+ known Roblox/Unity event names (exact match), `On*`
prefix with uppercase-third-char guard (avoids `OnGround` false positives), and
pattern suffixes (`Event`, `Changed`, `Completed`, `Started`, `Ended`, `Triggered`,
`Clicked`, `Pressed`, `Released`).

---

## Resolved

### ~~C# → Luau Transpiler Regex Pipeline~~

**Status**: RESOLVED (2026-03-04)
**Commit**: `8494bdd` — Replaced 73+ sequential regex substitutions with AST-driven
tree-sitter emitter (`_LuauEmitter` class). Regex preserved as fallback.
**Skill**: `review-csharp-lua-conversion`

---

### ~~C# → Luau Transpiler Coverage Gaps~~

**Status**: RESOLVED (2026-03-04)
**Commit**: `2fcfe3a` — Added AST emitter handlers + regex fallback for three
previously-unsupported C# patterns.

| # | Gap | Resolution |
|---|-----|------------|
| 1 | ~~Coroutines (`IEnumerator`, `yield return`, `WaitForSeconds`)~~ | RESOLVED — `_emit_yield_statement` converts yields to `task.wait()`; `IEnumerator` methods wrapped in `task.spawn(function() ... end)` |
| 2 | ~~Event subscriptions (`+=`/`-=` on delegates)~~ | RESOLVED — `_emit_assignment_expression` detects event-like targets (`On*`, `*Event`, `*Changed`, `onClick`, etc.) and emits `:Connect(handler)` |
| 3 | ~~String interpolation (`$"text {expr}"`)~~ | RESOLVED — `_emit_interpolated_string_expression` walks AST interpolation nodes and emits `string.format("text %s", tostring(expr))` |
| 4 | ~~Lambda / anonymous delegates~~ | RESOLVED — `_emit_lambda_expression` and `_emit_anonymous_method_expression` convert to `function(...) ... end` |

**Skill**: `review-csharp-lua-conversion`
