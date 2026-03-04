# Skill: Harden Unity YAML Parsing

## Goal

Fix the five structural fragilities in `modules/unity_yaml_utils.py`,
`modules/scene_parser.py`, and `modules/prefab_parser.py` that cause silent
data loss on real Unity projects.

## Context

Unity serializes scenes/prefabs as multi-document YAML with custom `!u!` tags
and `&fileID` anchors.  The current parser uses a regex to extract document
headers, strips them, then feeds the cleaned text to `yaml.safe_load_all`.
This approach has five compounding issues detailed below.

## Fixes Required

### 1. Support negative fileIDs in document separator regex

**File**: `unity_yaml_utils.py:30`
**Current**: `UNITY_DOC_SEPARATOR = re.compile(r"^--- !u!(\d+) &(\d+).*$", re.MULTILINE)`
**Problem**: `(\d+)` rejects negative fileIDs like `&-4850089497005498858`, silently
dropping all Prefab Variant documents (standard since Unity 2018.3).
**Fix**: Change to `(-?\d+)` for the fileID capture group.

### 2. Track `stripped` documents

**File**: `unity_yaml_utils.py:30` and downstream consumers
**Problem**: Documents ending with `stripped` are partial overrides — they lack
fields that exist in the base prefab.  The parser treats them as full documents,
producing wrong defaults (position=0,0,0, name="GameObject").
**Fix**: Capture the `stripped` suffix in the separator regex.  Return it as part
of the document metadata.  Downstream parsers should skip stripped documents or
mark them as requiring base-prefab merging.

### 3. Per-document error recovery

**File**: `unity_yaml_utils.py:115-118`
**Current**: `except yaml.YAMLError: return []` — one bad document drops the entire file.
**Fix**: Instead of `yaml.safe_load_all` (which stops on first error), iterate
documents manually.  Parse each document individually with `yaml.safe_load`.
Split the cleaned text on `---` separators and parse each chunk.  Log errors
per-document but continue with the rest.

### 4. Align prefab parser component allowlist with scene parser

**File**: `prefab_parser.py:118-119` vs `scene_parser.py:185-193`
**Problem**: Scene parser recognizes 15 component classIDs; prefab parser only 4.
Colliders, rigidbodies, lights, cameras, particles, animators silently lost.
**Fix**: Extract the allowlist to a shared constant in `unity_yaml_utils.py`
(or `config.py`) and import it in both parsers.

### 5. Guard against `None` iteration on optional list fields

**File**: `scene_parser.py:310`, `prefab_parser.py:205` (and similar patterns)
**Problem**: `for mat_ref in body.get("m_Materials", []):` crashes with TypeError
if `m_Materials` is `None` (Unity serializes empty arrays as null in some versions).
**Fix**: Use `body.get("m_Materials") or []` instead of `body.get("m_Materials", [])`.
The `or []` handles both missing keys AND explicit `None` values.

## Verification

```bash
python -m pytest tests/test_scene_parser.py tests/test_scene_parser_detailed.py \
       tests/test_prefab_parser.py tests/test_prefab_parser_detailed.py -v
```

Add new tests for:
- Scene file with negative fileIDs (should parse, not drop documents)
- Scene file with `stripped` documents (should not produce wrong defaults)
- Malformed YAML in one document (other documents should still parse)
- Prefab with collider/rigidbody components (should be captured, not dropped)
- Material list that is `null` (should not crash)

## References

- Unity YAML serialization: https://docs.unity3d.com/Manual/FormatDescription.html
- Prefab Variants (Unity 2018.3+): negative fileIDs for internal references
- `docs/FRAGILITY_AUDIT.md` — P0 section
