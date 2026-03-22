# Implementation Tasks

One-shot engineering tasks for hardening and improving the converter pipeline. Each task references the relevant section of `docs/FRAGILITY_AUDIT.md`.

---

## P0: Harden Unity YAML Parsing

**Goal:** Fix five structural fragilities in `modules/unity_yaml_utils.py`, `modules/scene_parser.py`, and `modules/prefab_parser.py` that cause silent data loss on real Unity projects.

**Context:** Unity serializes scenes/prefabs as multi-document YAML with custom `!u!` tags and `&fileID` anchors. The current parser uses a regex to extract document headers, strips them, then feeds the cleaned text to `yaml.safe_load_all`. This approach has five compounding issues:

### Fix 1: Support negative fileIDs in document separator regex

**File:** `unity_yaml_utils.py:30`
**Current:** `UNITY_DOC_SEPARATOR = re.compile(r"^--- !u!(\d+) &(\d+).*$", re.MULTILINE)`
**Problem:** `(\d+)` rejects negative fileIDs like `&-4850089497005498858`, silently dropping all Prefab Variant documents (standard since Unity 2018.3).
**Fix:** Change to `(-?\d+)` for the fileID capture group.

### Fix 2: Track `stripped` documents

**File:** `unity_yaml_utils.py:30` and downstream consumers
**Problem:** Documents ending with `stripped` are partial overrides — they lack fields that exist in the base prefab. The parser treats them as full documents, producing wrong defaults.
**Fix:** Capture the `stripped` suffix in the separator regex. Downstream parsers should skip stripped documents or mark them as requiring base-prefab merging.

### Fix 3: Per-document error recovery

**File:** `unity_yaml_utils.py:115-118`
**Current:** `except yaml.YAMLError: return []` — one bad document drops the entire file.
**Fix:** Parse each document individually with `yaml.safe_load`. Log errors per-document but continue with the rest.

### Fix 4: Align prefab parser component allowlist with scene parser

**File:** `prefab_parser.py:118-119` vs `scene_parser.py:185-193`
**Problem:** Scene parser recognizes 15 component classIDs; prefab parser only 4.
**Fix:** Extract the allowlist to a shared constant in `unity_yaml_utils.py` or `config.py`.

### Fix 5: Guard against `None` iteration on optional list fields

**File:** `scene_parser.py:310`, `prefab_parser.py:205`
**Problem:** `body.get("m_Materials", [])` crashes if `m_Materials` is `None`.
**Fix:** Use `body.get("m_Materials") or []`.

**Verification:**
```bash
python -m pytest tests/test_scene_parser.py tests/test_scene_parser_detailed.py \
       tests/test_prefab_parser.py tests/test_prefab_parser_detailed.py -v
```

**Reference:** `docs/FRAGILITY_AUDIT.md` — P0 section

---

## P1a: Harden Asset Extraction

**Goal:** Add per-file error recovery to `modules/asset_extractor.py` so that a single corrupt file, broken symlink, or permission error does not crash the entire pipeline.

### Fix 1: Wrap per-file body in try/except

**File:** `asset_extractor.py:93-114`
**Fix:** Add `try/except OSError` around per-file processing. On error, append a warning to `manifest.warnings` and `continue`.

### Fix 2: Add a warnings field to AssetManifest

If `AssetManifest` does not already have a `warnings` field, add one.

**Verification:**
```bash
python -m pytest tests/test_asset_extractor.py tests/test_asset_extractor_detailed.py -v
```

**Reference:** `docs/FRAGILITY_AUDIT.md` — P1a section

---

## P1b: Fix RBXL Asset ID Patching

**Goal:** Replace fragile `str.replace()` calls in `modules/roblox_uploader.py` with XML-aware replacement so patching doesn't corrupt embedded Luau scripts.

### Fix 1: Parse RBXL as XML, replace only in URL properties

**File:** `roblox_uploader.py:311-321`
**Current:** `content.replace(f"rbxassetid://{local_name}", rbx_url)`
**Fix:** Parse with `xml.etree.ElementTree`. Only replace in `<url>` and `<Content>` elements, never in `<ProtectedString>` (script source).

### Fix 2: Distinguish HTTP error codes in upload failures

**File:** `roblox_uploader.py:389-449`
**Fix:** Catch `urllib.error.HTTPError` separately, distinguish 401 (auth), 403 (permission), 429 (rate limit) from 500 (server error).

**Verification:**
```bash
python -m pytest tests/test_roblox_uploader.py tests/test_roblox_uploader_detailed.py -v
```

**Reference:** `docs/FRAGILITY_AUDIT.md` — P1b section

---

## P2a: Fix Luau Validator Comment/String Stripping

**Goal:** Fix false positives in `modules/code_validator.py` caused by incorrect Luau string and comment handling.

### Fix 1: Handle Luau level-N long strings

**File:** `code_validator.py:68-77`
**Problem:** Only `[[...]]` (level 0) is stripped. Luau supports `[=[...]=]`, `[==[...]==]`, etc.
**Fix:** Use regex `\[(=*)\[.*?\]\1\]` with `re.DOTALL`.

### Fix 2: Fix comment stripping order

**File:** `code_validator.py:68-77`
**Problem:** Single-line `--` stripping runs before `--[[ ]]` block comment removal.
**Fix:** Strip block comments first, then single-line comments.

**Verification:**
```bash
python -m pytest tests/test_code_validator.py tests/test_code_validator_detailed.py -v
```

**Reference:** `docs/FRAGILITY_AUDIT.md` — P2a section

---

## P2b: Review Material Mapper Coverage

**Goal:** Expand shader coverage, add missing-dependency warnings, and improve error reporting in `modules/material_mapper.py`.

### Fix 1: Expand `_BUILTIN_SHADERS` table

**File:** `material_mapper.py:136-147`
**Missing:** UI/Default, Unlit/Texture, Unlit/Color, Unlit/Transparent, Transparent/Diffuse, Transparent/Specular, Self-Illumin, Mobile/Diffuse, Skybox shaders, Nature/Tree shaders, TextMeshPro shaders.

### Fix 2: Warn when Pillow is missing

**File:** `material_mapper.py:1149-1153`
**Current:** `except ImportError: return []` — silently skips ALL texture processing.
**Fix:** Add warning: `"Pillow (PIL) not installed — texture processing skipped"`.

### Fix 3: Log per-texture errors

**File:** `material_mapper.py:1504-1506`
**Current:** `except Exception: continue` — no logging.
**Fix:** Append a warning per failed texture with filename and error message.

### Fix 4: Reuse unity_yaml_utils for YAML parsing

**File:** `material_mapper.py:321-326`
**Fix:** Use `unity_yaml_utils.load_unity_yaml()` or import the shared header-stripping regex.

### Fix 5: Improve specular-to-metallic conversion

**File:** `material_mapper.py:813-843`
**Current:** Binary threshold (luminance > 0.5 → metallic=1.0, else 0.0).
**Fix:** Use continuous mapping: `metallic = clamp(luminance * 2 - 0.5, 0, 1)`.

**Verification:**
```bash
python -m pytest tests/test_material_mapper.py tests/test_material_mapper_detailed.py -v
```

**Reference:** `docs/FRAGILITY_AUDIT.md` — P2b section

---

## P3: Consolidate Asset Type Extension Maps

**Goal:** Unify three divergent `_EXT_TO_KIND` / `SUPPORTED_ASSET_EXTENSIONS` maps into a single source of truth.

**Context:** Three files define independent extension→type mappings that have drifted apart:
- `modules/guid_resolver.py` — 21 extensions (most comprehensive)
- `modules/asset_extractor.py` — 13 extensions (subset)
- `config.py` — `SUPPORTED_ASSET_EXTENSIONS` set (includes `.asset` which neither module has)

### Fix 1: Define canonical map in config.py

Create `ASSET_EXT_TO_KIND: dict[str, str]` merging all three lists.

### Fix 2: Import in both modules

Replace local `_EXT_TO_KIND` dicts with imports from `config.py`.

### Fix 3: Derive SUPPORTED_ASSET_EXTENSIONS from the canonical map

`SUPPORTED_ASSET_EXTENSIONS = frozenset(ASSET_EXT_TO_KIND.keys())`

**Verification:**
```bash
python -m pytest tests/ --ignore=tests/test_converter_e2e.py \
       --ignore=tests/test_vertex_color_baker.py -v
```

**Reference:** `docs/FRAGILITY_AUDIT.md` — P3 section
