# Skill: Consolidate Asset Type Extension Maps

## Goal

Unify the three divergent `_EXT_TO_KIND` / `SUPPORTED_ASSET_EXTENSIONS` maps
into a single source of truth.

## Context

Three files define independent extension→type mappings that have drifted apart:
- `modules/guid_resolver.py` — 21 extensions (most comprehensive)
- `modules/asset_extractor.py` — 13 extensions (subset)
- `config.py` — `SUPPORTED_ASSET_EXTENSIONS` set (includes `.asset` which neither module has)

## Fixes Required

### 1. Define canonical map in config.py

**File**: `config.py`
**Fix**: Create a single `ASSET_EXT_TO_KIND: dict[str, str]` that merges all
three lists.  Include all extensions from `guid_resolver` plus `.asset` from
`config.py`.

### 2. Import in both modules

**Files**: `guid_resolver.py`, `asset_extractor.py`
**Fix**: Replace local `_EXT_TO_KIND` dicts with imports from `config.py`.
The `asset_extractor` can filter to only "extractable" kinds if needed, but
the base mapping should be shared.

### 3. Derive SUPPORTED_ASSET_EXTENSIONS from the canonical map

**File**: `config.py`
**Fix**: `SUPPORTED_ASSET_EXTENSIONS = frozenset(ASSET_EXT_TO_KIND.keys())`

## Verification

```bash
python -m pytest tests/ --ignore=tests/test_converter_e2e.py \
       --ignore=tests/test_vertex_color_baker.py -v
```

## References

- `docs/FRAGILITY_AUDIT.md` — P3 section
